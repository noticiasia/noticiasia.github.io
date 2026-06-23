import requests
from bs4 import BeautifulSoup
from google import genai
import os
import time
import random
from datetime import datetime, timedelta # <-- NUEVO: Para manejar la hora de las noticias

# --- 1. CONFIGURACIÓN DE LA IA ---
API_KEY = os.environ.get("LLAVESECRETABRAI")
client = genai.Client(api_key=API_KEY)

# --- 2. EL RECOLECTOR MULTI-FUENTE (Nuevas fuentes financieras) ---
fuentes = [
    {"nombre": "ÁMBITO", "url": "https://www.ambito.com/", "base": "https://www.ambito.com"},
    {"nombre": "INFOBAE", "url": "https://www.infobae.com/", "base": "https://www.infobae.com"},
    {"nombre": "TN", "url": "https://tn.com.ar/", "base": "https://tn.com.ar"},
    {"nombre": "OLÉ", "url": "https://www.ole.com.ar/", "base": "https://www.ole.com.ar"},
    {"nombre": "CRONISTA", "url": "https://www.cronista.com/", "base": "https://www.cronista.com"},
    {"nombre": "IPROFESIONAL", "url": "https://www.iprofesional.com/", "base": "https://www.iprofesional.com"},
    {"nombre": "YAHOO FINANZAS", "url": "https://es.finance.yahoo.com/", "base": "https://es.finance.yahoo.com"}
]

encabezados = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
noticias_extraidas = []

for fuente in fuentes:
    try:
        respuesta = requests.get(fuente["url"], headers=encabezados, timeout=10)
        if respuesta.status_code == 200:
            sopa = BeautifulSoup(respuesta.text, 'html.parser')
            articulos = sopa.find_all(['h2', 'h1']) 
            contador = 0
            
            for articulo in articulos:
                texto_limpio = articulo.text.strip()
                enlace_tag = articulo.find('a')
                if enlace_tag and 'href' in enlace_tag.attrs:
                    link = enlace_tag['href']
                    if not link.startswith('http'):
                        link = fuente["base"] + link
                    
                    if len(texto_limpio) > 25: 
                        noticias_extraidas.append({"fuente": fuente["nombre"], "titulo": texto_limpio, "link": link})
                        contador += 1
                        if contador >= 4: # 4 noticias por cada uno de los 7 diarios
                            break
    except Exception as e:
        pass

random.shuffle(noticias_extraidas)
noticias_finales = noticias_extraidas[:14] # ¡Aumentamos a 14 noticias por ronda!

texto_para_ia = ""
for i, noticia in enumerate(noticias_finales):
    texto_para_ia += f"Noticia {i+1} [{noticia['fuente']}]:\n- Título: {noticia['titulo']}\n- Link: {noticia['link']}\n\n"

# --- 3. EL CEREBRO ---
prompt = f"""
Eres un editor experto de noticias. Aquí tienes {len(noticias_finales)} noticias de hoy:
{texto_para_ia}

Devuelve la información en este formato por cada noticia, separando con el símbolo |.
Clasifica obligatoriamente cada noticia en: DEPORTES, SOCIEDAD, POLÍTICA, ECONOMÍA, MERCADOS o TECNOLOGÍA. 
(Usa MERCADOS exclusivamente para bolsa, trading, bonos, acciones, CEDEARs, dólar y Wall Street).
Escribe un RESUMEN EXTENDIDO de entre 40 y 60 palabras, brindando detalles profundos.

Formato:
DIARIO|CATEGORIA|TÍTULO|RESUMEN EXTENDIDO|LINK
"""

max_intentos = 3
exito = False
respuesta_ia_texto = ""

for intento in range(max_intentos):
    try:
        respuesta_ia = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        respuesta_ia_texto = respuesta_ia.text
        exito = True
        break
    except Exception as e:
        time.sleep(10)

if not exito:
    try:
        respuesta_ia = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
        respuesta_ia_texto = respuesta_ia.text
        exito = True
    except:
        pass

if exito:
    lineas = respuesta_ia_texto.strip().split('\n')
    tarjetas_html = ""
    
    for linea in lineas:
        if "|" in linea:
            partes = linea.split("|")
            if len(partes) >= 5:
                fuente_diario = partes[0].strip().upper()
                categoria = partes[1].strip().upper()
                titulo = partes[2].strip()
                resumen = partes[3].strip()
                link = partes[4].strip()
                
                # --- NUEVOS COLORES ESTÉTICOS ---
                if categoria == "MERCADOS":
                    borde, pill = "border-emerald-500", "bg-emerald-900/40 text-emerald-400"
                elif categoria == "ECONOMÍA":
                    borde, pill = "border-blue-500", "bg-blue-900/40 text-blue-400"
                elif categoria == "DEPORTES":
                    borde, pill = "border-orange-500", "bg-orange-900/40 text-orange-400"
                elif categoria == "POLÍTICA":
                    borde, pill = "border-indigo-500", "bg-indigo-900/40 text-indigo-400"
                elif categoria == "TECNOLOGÍA":
                    borde, pill = "border-violet-500", "bg-violet-900/40 text-violet-400"
                else: # Sociedad y General
                    borde, pill = "border-teal-500", "bg-teal-900/40 text-teal-400"
                
                # Simular un tiempo realista de publicación (entre 1 min y 3 horas atrás)
                minutos_restar = random.randint(1, 180)
                tiempo_simulado = datetime.now() - timedelta(minutes=minutos_restar)
                timestamp_iso = tiempo_simulado.isoformat()
                
                tarjetas_html += f"""
                <article data-categoria="{categoria}" class="tarjeta-noticia bg-[#111827] rounded-xl p-6 flex flex-col border-l-4 {borde} hover:scale-[1.02] transition-transform duration-300 shadow-lg shadow-black/50">
                    <div class="flex justify-between items-center mb-4 text-xs font-bold tracking-wide">
                        <div class="flex gap-2">
                            <span class="bg-[#1f2937] text-gray-300 px-2.5 py-1 rounded-md border border-gray-700">{fuente_diario}</span>
                            <span class="{pill} px-2.5 py-1 rounded-md">{categoria}</span>
                        </div>
                        <span class="tiempo-noticia text-gray-500 text-right" data-timestamp="{timestamp_iso}">Reciente</span>
                    </div>
                    <h2 class="text-xl font-bold text-white mb-3 leading-tight">{titulo}</h2>
                    <p class="text-gray-400 text-sm mb-6 flex-grow leading-relaxed">{resumen}</p>
                    <a href="{link}" target="_blank" class="text-cyan-400 text-sm font-semibold hover:text-cyan-300 hover:underline flex justify-start items-center gap-1 mt-auto">
                        Leer nota completa &rarr;
                    </a>
                </article>
                """
    
    # --- LA MAGIA DEL HISTORIAL ---
    historial_viejo = ""
    if os.path.exists("historial.txt"):
        with open("historial.txt", "r", encoding="utf-8") as f:
            historial_viejo = f.read()
            
    historial_actualizado = tarjetas_html + "\n" + historial_viejo
    
    with open("historial.txt", "w", encoding="utf-8") as f:
        f.write(historial_actualizado)
        
    # --- PLANTILLA HTML (Nuevo Diseño y Reloj JS) ---
    html_completo = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Noticias IA | Mercados & Actualidad</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>body {{ background-color: #0b0f19; font-family: 'Inter', sans-serif; scroll-behavior: smooth; }}</style>
</head>
<body class="text-gray-300 antialiased min-h-screen pb-12">
    
    <nav class="flex justify-between items-center px-8 py-5 border-b border-[#1f2937] bg-[#0b0f19]/90 backdrop-blur-md sticky top-0 z-50">
        <div class="text-2xl font-black text-white flex items-center gap-2">Noticias IA 🤖</div>
        <div class="hidden md:flex gap-6 text-sm font-semibold text-gray-400">
            <a href="#" class="hover:text-cyan-400 transition">Noticias</a>
            <a href="#contacto" class="hover:text-cyan-400 transition">Contacto</a>
        </div>
    </nav>
    
    <header class="text-center mt-16 mb-12 px-4">
        <h1 class="text-4xl md:text-5xl font-black text-white mb-6 tracking-tight">
            La información al <span class="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">instante</span>
        </h1>
        <p class="text-gray-400 max-w-2xl mx-auto text-lg">Noticias y Mercados en tiempo real, analizadas a fondo por Inteligencia Artificial.</p>
    </header>

    <div class="max-w-4xl mx-auto px-4 flex flex-wrap justify-center gap-3 mb-12">
        <button data-filter="TODAS" class="btn-filtro bg-gradient-to-r from-cyan-400 to-blue-500 text-black px-5 py-2.5 rounded-full font-bold text-sm transition shadow-lg shadow-cyan-500/20">Todas</button>
        <button data-filter="MERCADOS" class="btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50">Mercados</button>
        <button data-filter="ECONOMÍA" class="btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50">Economía</button>
        <button data-filter="POLÍTICA" class="btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50">Política</button>
        <button data-filter="DEPORTES" class="btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50">Deportes</button>
        <button data-filter="SOCIEDAD" class="btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50">Sociedad</button>
        <button data-filter="TECNOLOGÍA" class="btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50">Tecnología</button>
    </div>

    <main class="max-w-6xl mx-auto px-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-20">
        {historial_actualizado}
    </main>

    <section id="contacto" class="max-w-5xl mx-auto px-4 mt-20 border-t border-[#1f2937] pt-16">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-10">
            <div class="flex flex-col gap-4 justify-center">
                <a href="#" class="bg-[#111827] border border-[#1f2937] hover:border-cyan-500/50 rounded-xl p-5 flex items-center gap-4 transition group">
                    <div class="bg-cyan-500 text-black p-2 rounded text-xl font-black group-hover:scale-110 transition">in</div>
                    <span class="text-white font-semibold">Conectá conmigo en LinkedIn</span>
                </a>
                <a href="mailto:tu-email@ejemplo.com" class="bg-[#111827] border border-[#1f2937] hover:border-cyan-500/50 rounded-xl p-5 flex items-center gap-4 transition group">
                    <div class="text-cyan-500 text-2xl group-hover:scale-110 transition">✉</div>
                    <span class="text-white font-semibold">tu-email@ejemplo.com</span>
                </a>
            </div>
            
            <div class="bg-[#111827] border border-[#1f2937] rounded-2xl p-8 shadow-xl">
                <form class="flex flex-col gap-5">
                    <div>
                        <label class="block text-sm font-semibold text-gray-400 mb-2">Nombre</label>
                        <input type="text" placeholder="Tu nombre" class="w-full bg-[#1f2937] border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-cyan-500 transition">
                    </div>
                    <div>
                        <label class="block text-sm font-semibold text-gray-400 mb-2">Email</label>
                        <input type="email" placeholder="tu@email.com" class="w-full bg-[#1f2937] border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-cyan-500 transition">
                    </div>
                    <div>
                        <label class="block text-sm font-semibold text-gray-400 mb-2">Mensaje</label>
                        <textarea rows="4" placeholder="¿En qué puedo ayudarte?" class="w-full bg-[#1f2937] border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-cyan-500 transition resize-none"></textarea>
                    </div>
                    <button type="button" class="w-full bg-gradient-to-r from-cyan-400 to-blue-500 hover:from-cyan-500 hover:to-blue-600 text-black font-bold py-3 px-4 rounded-lg flex justify-center items-center gap-2 transition shadow-lg shadow-cyan-500/20 mt-2">
                        Enviar Mensaje <span>🚀</span>
                    </button>
                </form>
            </div>
        </div>
    </section>

    <script>
        // Lógica de Filtros
        const botones = document.querySelectorAll('.btn-filtro');
        const articulos = document.querySelectorAll('.tarjeta-noticia');

        botones.forEach(boton => {{
            boton.addEventListener('click', () => {{
                botones.forEach(b => b.className = 'btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50');
                boton.className = 'btn-filtro bg-gradient-to-r from-cyan-400 to-blue-500 text-black px-5 py-2.5 rounded-full font-bold text-sm shadow-lg shadow-cyan-500/20 transition';
                
                const categoriaElegida = boton.getAttribute('data-filter');
                articulos.forEach(art => {{
                    if (categoriaElegida === 'TODAS' || art.getAttribute('data-categoria') === categoriaElegida) {{
                        art.style.display = 'flex';
                    }} else {{
                        art.style.display = 'none';
                    }}
                }});
            }});
        }});

        // Lógica del Reloj en Vivo (hace 2 min, hace 3 h)
        function actualizarTiempos() {{
            document.querySelectorAll('.tiempo-noticia').forEach(el => {{
                const timestampStr = el.getAttribute('data-timestamp');
                if(!timestampStr) return; // Si es una tarjeta vieja sin fecha, la ignora
                
                const fechaNoticia = new Date(timestampStr);
                const ahora = new Date();
                const diffMinutos = Math.floor((ahora - fechaNoticia) / 60000);
                
                if (diffMinutos < 1) {{
                    el.textContent = "Hace instantes";
                }} else if (diffMinutos < 60) {{
                    el.textContent = `hace ${{diffMinutos}} min`;
                }} else {{
                    const diffHoras = Math.floor(diffMinutos / 60);
                    el.textContent = `hace ${{diffHoras}} h`;
                }}
            }});
        }}
        
        // Ejecuta el reloj ni bien carga la página y luego lo actualiza cada minuto
        actualizarTiempos();
        setInterval(actualizarTiempos, 60000);
    </script>
</body>
</html>"""
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_completo)
