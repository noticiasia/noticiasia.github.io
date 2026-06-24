import requests
from bs4 import BeautifulSoup
from google import genai
import os
import time
import random
import json
from datetime import datetime, timezone

# --- 1. CONFIGURACIÓN DE LA IA ---
API_KEY = os.environ.get("LLAVESECRETABRAI")
client = genai.Client(api_key=API_KEY)

# --- 2. EL RECOLECTOR MULTI-FUENTE (6 Fuentes Sólidas) ---
fuentes = [
    {"nombre": "ÁMBITO", "url": "https://www.ambito.com/", "base": "https://www.ambito.com"},
    {"nombre": "INFOBAE", "url": "https://www.infobae.com/", "base": "https://www.infobae.com"},
    {"nombre": "TN", "url": "https://tn.com.ar/", "base": "https://tn.com.ar"},
    {"nombre": "IPROFESIONAL", "url": "https://www.iprofesional.com/", "base": "https://www.iprofesional.com"},
    {"nombre": "YAHOO FINANZAS", "url": "https://es.finance.yahoo.com/", "base": "https://es.finance.yahoo.com"},
    {"nombre": "LA NACION", "url": "https://www.lanacion.com.ar/", "base": "https://www.lanacion.com.ar"}
]

encabezados = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
noticias_extraidas = []
urls_vistas_ronda_actual = set()

palabras_prohibidas = ["javascript", "mailto", "defensa-del-consumidor", "/autor/", "/tema/", "/tags/", "redaccion"]

for fuente in fuentes:
    try:
        respuesta = requests.get(fuente["url"], headers=encabezados, timeout=10)
        if respuesta.status_code == 200:
            sopa = BeautifulSoup(respuesta.text, 'html.parser')
            contador = 0
            
            articulos = sopa.find_all(['article', 'h1', 'h2', 'h3', 'h4']) 
            for articulo in articulos:
                texto_limpio = " ".join(articulo.text.split())
                
                if len(texto_limpio) < 20:
                    continue
                
                enlace_tag = articulo.find('a')
                if not enlace_tag:
                    padres = articulo.find_parents('a')
                    if padres:
                        enlace_tag = padres[0]
                
                if enlace_tag and 'href' in enlace_tag.attrs:
                    link = enlace_tag['href']
                    
                    if any(prohibido in link.lower() for prohibido in palabras_prohibidas):
                        continue
                        
                    if not link.startswith('http'):
                        if not link.startswith('/'):
                            link = '/' + link
                        link = fuente["base"] + link
                    
                    if link not in urls_vistas_ronda_actual:
                        urls_vistas_ronda_actual.add(link)
                        noticias_extraidas.append({"fuente": fuente["nombre"], "titulo": texto_limpio, "link": link})
                        contador += 1
                        if contador >= 4: 
                            break
    except Exception as e:
        pass

random.shuffle(noticias_extraidas)
noticias_finales = noticias_extraidas[:14]

# --- MOTOR FORENSE DE EXTRACCIÓN DE HORA ---
print("Extrayendo metadatos de tiempo...")
tiempos_reales = {}

def extraer_fecha_exacta(sopa):
    metas = ['article:published_time', 'article:modified_time', 'datePublished', 'pubdate']
    for m in metas:
        tag = sopa.find('meta', property=m) or sopa.find('meta', itemprop=m) or sopa.find('meta', attrs={'name': m})
        if tag and tag.get('content'):
            return tag['content']
    
    scripts = sopa.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            if script.string:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    if 'datePublished' in data: return data['datePublished']
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and 'datePublished' in item:
                            return item['datePublished']
        except:
            pass
    return None

for noticia in noticias_finales:
    link_nota = noticia['link']
    hora_fallback = datetime.now(timezone.utc).isoformat()
    tiempos_reales[link_nota] = hora_fallback 
    
    try:
        resp_nota = requests.get(link_nota, headers=encabezados, timeout=5)
        if resp_nota.status_code == 200:
            sopa_nota = BeautifulSoup(resp_nota.text, 'html.parser')
            fecha_encontrada = extraer_fecha_exacta(sopa_nota)
            if fecha_encontrada:
                tiempos_reales[link_nota] = fecha_encontrada
    except:
        pass

texto_para_ia = ""
for i, noticia in enumerate(noticias_finales):
    texto_para_ia += f"Noticia {i+1} [{noticia['fuente']}]:\n- Título: {noticia['titulo']}\n- Link: {noticia['link']}\n\n"

# --- 3. EL CEREBRO DE LA IA ---
prompt = f"""
Eres un editor experto de noticias. Aquí tienes {len(noticias_finales)} noticias de hoy:
{texto_para_ia}

REGLAS ESTRICTAS:
1. Clasifica obligatoriamente cada noticia en una de estas 4 categorías: DEPORTES, POLÍTICA, ECONOMÍA o MERCADOS. (MERCADOS es solo para bolsa, dólar, trading). ESTÁ PROHIBIDO USAR LA CATEGORÍA "SOCIEDAD" O "TECNOLOGÍA".
2. Escribe un RESUMEN EXTENDIDO de entre 40 y 60 palabras, brindando detalles profundos.

Devuelve la información en este formato por cada noticia, separando con el símbolo |:
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
                
                # GUILLOTINA DE TIEMPO
                timestamp_iso = tiempos_reales.get(link, datetime.now(timezone.utc).isoformat())
                try:
                    dt_noticia = datetime.fromisoformat(timestamp_iso.replace('Z', '+00:00'))
                    if dt_noticia.tzinfo is None:
                        dt_noticia = dt_noticia.replace(tzinfo=timezone.utc)
                    
                    diferencia_horas = (datetime.now(timezone.utc) - dt_noticia).total_seconds() / 3600
                    
                    if diferencia_horas > 24:
                        continue 
                except:
                    pass
                
                if categoria == "MERCADOS":
                    borde, pill = "border-emerald-500", "bg-emerald-900/40 text-emerald-400"
                elif categoria == "ECONOMÍA":
                    borde, pill = "border-blue-500", "bg-blue-900/40 text-blue-400"
                elif categoria == "DEPORTES":
                    borde, pill = "border-orange-500", "bg-orange-900/40 text-orange-400"
                elif categoria == "POLÍTICA":
                    borde, pill = "border-indigo-500", "bg-indigo-900/40 text-indigo-400"
                else: 
                    borde, pill = "border-teal-500", "bg-teal-900/40 text-teal-400"
                
                tarjetas_html += f"""
                <article data-categoria="{categoria}" class="tarjeta-noticia bg-[#111827] rounded-xl p-6 flex flex-col border-l-4 {borde} hover:scale-[1.02] transition-transform duration-300 shadow-lg shadow-black/50">
                    <div class="flex justify-between items-center mb-4 text-xs font-bold tracking-wide">
                        <div class="flex gap-2">
                            <span class="bg-[#1f2937] text-gray-300 px-2.5 py-1 rounded-md border border-gray-700">{fuente_diario}</span>
                            <span class="{pill} px-2.5 py-1 rounded-md">{categoria}</span>
                        </div>
                        <span class="tiempo-noticia text-gray-500 text-right" data-timestamp="{timestamp_iso}">Reciente</span>
                    </div>
                    
                    <a href="{link}" target="_blank" class="group block mb-3">
                        <h2 class="text-xl font-bold text-white leading-tight group-hover:text-cyan-400 group-hover:underline transition duration-200 flex items-start gap-2">
                            <span>{titulo}</span>
                            <svg class="w-5 h-5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity text-cyan-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                        </h2>
                    </a>
                    
                    <p class="text-gray-400 text-sm flex-grow leading-relaxed">{resumen}</p>
                </article>
                """
    
    # --- PURGA DE FANTASMAS ---
    historial_viejo_limpio = ""
    if os.path.exists("historial.txt"):
        with open("historial.txt", "r", encoding="utf-8") as f:
            contenido_previo = f.read()
            
        sopa_vieja = BeautifulSoup(contenido_previo, 'html.parser')
        for tarjeta in sopa_vieja.find_all('article'):
            span_diario = tarjeta.find('span', class_=lambda c: c and 'bg-[#1f2937]' in c)
            if span_diario:
                nombre_diario = span_diario.text.strip().upper()
                if "CRONISTA" in nombre_diario or "FORBES" in nombre_diario or "BAE" in nombre_diario or "OLÉ" in nombre_diario:
                    tarjeta.decompose()
                    continue
            
            categoria_tarjeta = tarjeta.get('data-categoria', '').upper()
            if categoria_tarjeta not in ["DEPORTES", "POLÍTICA", "ECONOMÍA", "MERCADOS"]:
                tarjeta.decompose()
                
        historial_viejo_limpio = str(sopa_vieja)
            
    historial_completo_str = tarjetas_html + "\n" + historial_viejo_limpio
    
    # --- ORDENAMIENTO Y ANTI-DUPLICADOS ---
    sopa_historial = BeautifulSoup(historial_completo_str, 'html.parser')
    todos_los_articulos = sopa_historial.find_all('article')
    
    def obtener_fecha_segura(articulo):
        etiqueta_tiempo = articulo.find('span', class_='tiempo-noticia')
        if etiqueta_tiempo and etiqueta_tiempo.has_attr('data-timestamp'):
            fecha_str = etiqueta_tiempo['data-timestamp']
            try:
                dt = datetime.fromisoformat(fecha_str.replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except:
                pass
        return datetime.min.replace(tzinfo=timezone.utc)

    articulos_ordenados = sorted(todos_los_articulos, key=obtener_fecha_segura, reverse=True)
    
    urls_historial = set()
    articulos_unicos = []
    
    for articulo in articulos_ordenados:
        enlace = articulo.find('a', target="_blank")
        if enlace and 'href' in enlace.attrs:
            link_articulo = enlace['href']
            if link_articulo not in urls_historial:
                urls_historial.add(link_articulo)
                articulos_unicos.append(articulo)
        else:
            articulos_unicos.append(articulo)
    
    max_noticias = 60
    articulos_finales = articulos_unicos[:max_noticias]
    historial_recortado = "\n".join([str(art) for art in articulos_finales])
    
    with open("historial.txt", "w", encoding="utf-8") as f:
        f.write(historial_recortado)

    # --- 4. EXTRACCIÓN DEL MERCADO BURSÁTIL ---
    print("Obteniendo cotizaciones del mercado...")
    cotizaciones_html = ""
    try:
        req_api = requests.get("https://dolarapi.com/v1/dolares", timeout=10)
        if req_api.status_code == 200:
            datos_dolar = req_api.json()
            casas_clave = {"oficial": "DÓLAR OFICIAL", "blue": "DÓLAR BLUE", "bolsa": "DÓLAR MEP", "contadoconliqui": "DÓLAR CCL"}
            
            for casa, nombre_mostrar in casas_clave.items():
                for dolar in datos_dolar:
                    if dolar["casa"] == casa:
                        venta = dolar["venta"]
                        compra = dolar.get("compra", venta)
                        cotizaciones_html += f"""
                        <div class="bg-[#1f2937] border border-gray-700 rounded-xl p-4 flex-1 min-w-[140px] text-center shadow-lg hover:border-emerald-500/50 transition">
                            <h3 class="text-gray-400 text-xs font-bold tracking-widest mb-1">{nombre_mostrar}</h3>
                            <div class="text-2xl font-black text-emerald-400">${venta}</div>
                            <div class="text-[10px] text-gray-500 mt-1">Compra: ${compra}</div>
                        </div>
                        """
                        break
    except Exception as e:
        cotizaciones_html = "<div class='text-gray-500 text-sm text-center w-full'>Cotizaciones del mercado no disponibles temporalmente.</div>"

    panel_financiero = f"""
    <div class="max-w-4xl mx-auto px-4 mb-8">
        <div class="flex flex-wrap gap-4 justify-between">
            {cotizaciones_html}
        </div>
    </div>
    """
        
    # --- PLANTILLA HTML DEFINITIVA (Con SEO y solo LinkedIn) ---
    html_completo = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <title>Noticias IA | Mercados & Actualidad</title>
    <meta name="description" content="Portal de noticias financieras, mercado de capitales y actualidad argentina en tiempo real, analizadas a fondo por Inteligencia Artificial.">
    <meta property="og:title" content="Noticias IA | Mercados & Actualidad">
    <meta property="og:description" content="Portal de noticias financieras y actualidad en tiempo real, analizadas a fondo por Inteligencia Artificial.">
    <meta property="og:image" content="https://itu.uncuyo.edu.ar/cache/16c63c321040ab4da2010172ba336d67_732_1296.jpg"> <meta property="og:url" content="https://noticiasia.github.io/">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    
    <script src="https://cdn.tailwindcss.com"></script>
    <style>body {{ background-color: #0b0f19; font-family: 'Inter', sans-serif; scroll-behavior: smooth; }}</style>
</head>
<body class="text-gray-300 antialiased min-h-screen pb-12 flex flex-col">
    
    <nav class="flex justify-between items-center px-8 py-5 border-b border-[#1f2937] bg-[#0b0f19]/90 backdrop-blur-md sticky top-0 z-50">
        <div class="text-2xl font-black text-white flex items-center gap-2">Noticias IA 🤖</div>
    </nav>
    
    <header class="text-center mt-16 mb-10 px-4">
        <h1 class="text-4xl md:text-5xl font-black text-white mb-6 tracking-tight">
            La información al <span class="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500">instante</span>
        </h1>
        <p class="text-gray-400 max-w-2xl mx-auto text-lg mb-8">Noticias y Mercados en tiempo real, analizadas a fondo por Inteligencia Artificial.</p>
    </header>

    {panel_financiero}

    <div class="max-w-2xl mx-auto px-4 mb-8 mt-4 w-full">
        <div class="relative">
            <input type="text" id="buscador" placeholder="Buscar por palabra clave, acción o dólar..." class="w-full bg-[#111827] border border-[#1f2937] rounded-full px-6 py-4 text-white focus:outline-none focus:border-cyan-500 transition shadow-lg pl-14 placeholder-gray-500">
            <svg class="w-6 h-6 text-gray-500 absolute left-5 top-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
        </div>
    </div>

    <div class="max-w-4xl mx-auto px-4 flex flex-wrap justify-center gap-3 mb-12">
        <button data-filter="TODAS" class="btn-filtro bg-gradient-to-r from-cyan-400 to-blue-500 text-black px-5 py-2.5 rounded-full font-bold text-sm transition shadow-lg shadow-cyan-500/20">Todas</button>
        <button data-filter="MERCADOS" class="btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50">Mercados</button>
        <button data-filter="ECONOMÍA" class="btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50">Economía</button>
        <button data-filter="POLÍTICA" class="btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50">Política</button>
        <button data-filter="DEPORTES" class="btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50">Deportes</button>
    </div>

    <main class="max-w-6xl mx-auto px-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-20 flex-grow" id="contenedor-noticias">
        {historial_recortado}
    </main>

    <footer class="mt-auto border-t border-[#1f2937] pt-12 pb-6">
        <div class="max-w-md mx-auto px-4 flex justify-center">
            <a href="https://www.linkedin.com/in/brian-yapura-061522156/" target="_blank" class="bg-[#111827] border border-[#1f2937] hover:border-cyan-500/50 rounded-xl p-4 flex items-center gap-4 transition shadow-lg hover:shadow-cyan-500/10">
                <div class="bg-cyan-500 text-black px-2 py-1 rounded text-xl font-bold">in</div>
                <span class="text-white font-semibold">Conectá con Brian Hernan Yapura</span>
            </a>
        </div>
        <p class="text-center text-gray-600 text-xs mt-8">Generado automáticamente. Las noticias pertenecen a sus respectivos autores.</p>
    </footer>

    <script>
        const botones = document.querySelectorAll('.btn-filtro');
        const articulos = document.querySelectorAll('.tarjeta-noticia');
        const buscador = document.getElementById('buscador');
        let categoriaActual = 'TODAS';

        function filtrarNoticias() {{
            const textoBusqueda = buscador.value.toLowerCase();
            
            articulos.forEach(art => {{
                const categoriaArt = art.getAttribute('data-categoria');
                const titulo = art.querySelector('h2').textContent.toLowerCase();
                const resumen = art.querySelector('p').textContent.toLowerCase();
                
                const coincideCategoria = (categoriaActual === 'TODAS' || categoriaArt === categoriaActual);
                const coincideTexto = (titulo.includes(textoBusqueda) || resumen.includes(textoBusqueda));
                
                if (coincideCategoria && coincideTexto) {{
                    art.style.display = 'flex';
                }} else {{
                    art.style.display = 'none';
                }}
            }});
        }}

        botones.forEach(boton => {{
            boton.addEventListener('click', () => {{
                botones.forEach(b => b.className = 'btn-filtro bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition border border-gray-700 hover:border-cyan-500/50');
                boton.className = 'btn-filtro bg-gradient-to-r from-cyan-400 to-blue-500 text-black px-5 py-2.5 rounded-full font-bold text-sm shadow-lg shadow-cyan-500/20 transition';
                
                categoriaActual = boton.getAttribute('data-filter');
                filtrarNoticias();
            }});
        }});

        buscador.addEventListener('input', filtrarNoticias);

        function actualizarTiempos() {{
            document.querySelectorAll('.tiempo-noticia').forEach(el => {{
                const timestampStr = el.getAttribute('data-timestamp');
                if(!timestampStr) return; 
                
                const fechaNoticia = new Date(timestampStr);
                const ahora = new Date();
                const diffMinutos = Math.floor((ahora - fechaNoticia) / 60000);
                
                if (isNaN(diffMinutos)) return;

                if (diffMinutos < 1) {{
                    el.textContent = "Hace instantes";
                }} else if (diffMinutos < 60) {{
                    el.textContent = `hace ${{diffMinutos}} min`;
                }} else if (diffMinutos < 1440) {{
                    const diffHoras = Math.floor(diffMinutos / 60);
                    el.textContent = `hace ${{diffHoras}} h`;
                }} else {{
                    const diffDias = Math.floor(diffMinutos / 1440);
                    el.textContent = diffDias === 1 ? 'hace 1 día' : `hace ${{diffDias}} días`;
                }}
            }});
        }}
        
        actualizarTiempos();
        setInterval(actualizarTiempos, 60000);
    </script>
</body>
</html>"""
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_completo)
