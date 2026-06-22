import requests
from bs4 import BeautifulSoup
from google import genai
import os

# --- 1. CONFIGURACIÓN DE LA IA ---
API_KEY = os.environ.get("LLAVESECRETABRAI")
client = genai.Client(api_key=API_KEY)

# --- 2. EL RECOLECTOR (Ahora busca noticias generales) ---
url = "https://www.ambito.com/"
encabezados = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
respuesta = requests.get(url, headers=encabezados)

noticias_extraidas = []

if respuesta.status_code == 200:
    sopa = BeautifulSoup(respuesta.text, 'html.parser')
    articulos = sopa.find_all('h2')
    titulos_vistos = set()
    
    for articulo in articulos:
        texto_limpio = articulo.text.strip()
        enlace_tag = articulo.find('a')
        
        link = enlace_tag['href'] if enlace_tag and 'href' in enlace_tag.attrs else url
        if not link.startswith('http'):
            link = "https://www.ambito.com" + link
            
        if len(texto_limpio) > 15 and texto_limpio not in titulos_vistos:
            noticias_extraidas.append({"titulo": texto_limpio, "link": link})
            titulos_vistos.add(texto_limpio)
            if len(noticias_extraidas) == 3: # Buscamos las 3 noticias principales
                break
                
    texto_para_ia = ""
    for i, noticia in enumerate(noticias_extraidas):
        texto_para_ia += f"Noticia {i+1}:\n- Título: {noticia['titulo']}\n- Link: {noticia['link']}\n\n"

    # --- 3. EL CEREBRO ---
    prompt = f"""
    Eres un editor de noticias. Aquí tienes 3 noticias principales de hoy:
    {texto_para_ia}
    
    Devuelve ESTRICTAMENTE la información en este formato por cada noticia, separando con el símbolo |.
    Clasifica obligatoriamente cada noticia en UNA de estas categorías: DEPORTES, SOCIEDAD, POLÍTICA, ECONOMÍA, GENERAL.
    
    Formato:
    CATEGORIA|TÍTULO REFORMULADO|RESUMEN CORTO|LINK
    """
    
    try:
        respuesta_ia = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        
        # --- 4. ENSAMBLADOR WEB CON DISEÑO DINÁMICO ---
        lineas = respuesta_ia.text.strip().split('\n')
        tarjetas_html = ""
        
        for linea in lineas:
            if "|" in linea:
                partes = linea.split("|")
                if len(partes) >= 4:
                    categoria = partes[0].strip().upper()
                    titulo = partes[1].strip()
                    resumen = partes[2].strip()
                    link = partes[3].strip()
                    
                    # Lógica de colores según la categoría de la IA
                    if categoria == "DEPORTES":
                        borde = "border-emerald-500"
                        pill = "bg-emerald-900/40 text-emerald-400"
                    elif categoria == "SOCIEDAD":
                        borde = "border-purple-500"
                        pill = "bg-purple-900/40 text-purple-400"
                    elif categoria == "ECONOMÍA" or categoria == "POLÍTICA":
                        borde = "border-blue-500"
                        pill = "bg-blue-900/40 text-blue-400"
                    else:
                        borde = "border-gray-500"
                        pill = "bg-gray-800 text-gray-300"
                    
                    tarjetas_html += f"""
                    <article class="bg-[#111827] rounded-xl p-6 flex flex-col border-l-4 {borde} hover:scale-[1.02] transition-transform duration-300 shadow-lg">
                        <div class="flex justify-between items-center mb-4 text-xs font-bold tracking-wide">
                            <div class="flex gap-2">
                                <span class="bg-gray-800 text-gray-300 px-2.5 py-1 rounded-md">ÁMBITO</span>
                                <span class="{pill} px-2.5 py-1 rounded-md">{categoria}</span>
                            </div>
                            <span class="text-gray-500">Hace instantes</span>
                        </div>
                        <h2 class="text-xl font-bold text-white mb-3 leading-tight">{titulo}</h2>
                        <p class="text-gray-400 text-sm mb-6 flex-grow">{resumen}</p>
                        <a href="{link}" target="_blank" class="text-white text-sm font-semibold hover:underline flex justify-start items-center gap-1 mt-auto">
                            Leer nota original &rarr;
                        </a>
                    </article>
                    """
        
        # Plantilla con Navbar, Píldoras y Texto Degradado
        html_completo = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Noticias IA</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>body {{ background-color: #0b0f19; font-family: 'Inter', sans-serif; }}</style>
</head>
<body class="text-gray-300 antialiased min-h-screen pb-12">
    
    <nav class="flex justify-between items-center px-8 py-5 border-b border-gray-800 bg-[#0b0f19]">
        <div class="text-2xl font-black text-white flex items-center gap-2">Noticias IA 🤖</div>
        <div class="hidden md:flex gap-6 text-sm font-semibold text-gray-400">
            <a href="#" class="hover:text-white transition">Noticias</a>
            <a href="#" class="hover:text-white transition">Contacto</a>
        </div>
    </nav>
    
    <header class="text-center mt-16 mb-12 px-4">
        <h1 class="text-4xl md:text-5xl font-black text-white mb-6 tracking-tight">
            La información al <span class="text-transparent bg-clip-text bg-gradient-to-r from-yellow-400 to-orange-500">instante</span>
        </h1>
        <p class="text-gray-400 max-w-2xl mx-auto text-lg">Las noticias más relevantes de Argentina leídas, analizadas, categorizadas y resumidas por Inteligencia Artificial en tiempo real.</p>
    </header>

    <div class="max-w-4xl mx-auto px-4 flex flex-wrap justify-center gap-3 mb-12">
        <button class="bg-gradient-to-r from-yellow-400 to-orange-500 text-black px-5 py-2.5 rounded-full font-bold text-sm shadow-lg shadow-orange-500/20">
            Todas
        </button>
        <button class="bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition">Política</button>
        <button class="bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition">Economía</button>
        <button class="bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition">Deportes</button>
        <button class="bg-[#1f2937] text-gray-300 px-5 py-2.5 rounded-full font-semibold text-sm hover:bg-gray-700 transition">Sociedad</button>
    </div>

    <main class="max-w-6xl mx-auto px-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {tarjetas_html}
    </main>

</body>
</html>"""
        
        with open("index.html", "w", encoding="utf-8") as archivo:
            archivo.write(html_completo)
            
        print("¡Éxito! Web actualizada con el nuevo diseño avanzado.")
        
    except Exception as e:
        print("Error con la IA:", e)

else:
    print(f"Error al conectar. Código: {respuesta.status_code}")
