import requests
from bs4 import BeautifulSoup
from google import genai
import os

# --- 1. CONFIGURACIÓN DE LA IA ---
API_KEY = os.environ.get("LLAVESECRETABRAI")
client = genai.Client(api_key=API_KEY)

# --- 2. EL RECOLECTOR ---
url = "https://www.ambito.com/contenidos/finanzas.html"
encabezados = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
respuesta = requests.get(url, headers=encabezados)

noticias_extraidas = []

if respuesta.status_code == 200:
    sopa = BeautifulSoup(respuesta.text, 'html.parser')
    articulos = sopa.find_all('h2')
    palabras_clave = ["dólar", "bono", "cripto", "bitcoin", "riesgo", "wall street", "fed", "mercado", "tasa", "euro", "ypf", "merval", "eeuu", "inversión", "brecha"]
    titulos_vistos = set()
    
    for articulo in articulos:
        texto_limpio = articulo.text.strip()
        enlace_tag = articulo.find('a')
        
        # Extraemos el link real de la noticia
        link = enlace_tag['href'] if enlace_tag and 'href' in enlace_tag.attrs else url
        if not link.startswith('http'):
            link = "https://www.ambito.com" + link
            
        if len(texto_limpio) > 15 and texto_limpio not in titulos_vistos:
            if any(p in texto_limpio.lower() for p in palabras_clave):
                noticias_extraidas.append({"titulo": texto_limpio, "link": link})
                titulos_vistos.add(texto_limpio)
                if len(noticias_extraidas) == 3: # Tomamos solo las 3 primeras
                    break
                    
    # Preparamos los datos para la IA
    texto_para_ia = ""
    for i, noticia in enumerate(noticias_extraidas):
        texto_para_ia += f"Noticia {i+1}:\n- Título: {noticia['titulo']}\n- Link: {noticia['link']}\n\n"

    # --- 3. EL CEREBRO ---
    prompt = f"""
    Eres un analista financiero. Aquí tienes 3 noticias reales de hoy con sus enlaces:
    {texto_para_ia}
    
    Devuelve ESTRICTAMENTE la información en este formato por cada noticia, separando con el símbolo | (barra vertical). 
    No agregues introducciones, ni markdown, ni comillas.
    
    Formato exacto:
    CATEGORIA CORTA|TÍTULO REFORMULADO|RESUMEN DE 2 LÍNEAS|LINK EXACTO

    Ejemplo:
    DÓLAR|Sube el dólar blue|El mercado reacciona a las nuevas medidas con una fuerte demanda.|https://www.ambito.com/noticia-ejemplo
    """
    
    try:
        respuesta_ia = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        
        # --- 4. ENSAMBLADOR WEB BLINDADO ---
        lineas = respuesta_ia.text.strip().split('\n')
        tarjetas_html = ""
        
        for linea in lineas:
            if "|" in linea:
                partes = linea.split("|")
                if len(partes) >= 4:
                    categoria = partes[0].strip()
                    titulo = partes[1].strip()
                    resumen = partes[2].strip()
                    link = partes[3].strip()
                    
                    tarjetas_html += f"""
                    <article class="card-bg rounded-2xl p-6 border border-slate-700 flex flex-col hover:border-slate-500 transition">
                        <div class="flex justify-between items-center mb-4 text-xs font-semibold">
                            <div class="flex gap-2">
                                <span class="bg-slate-700 text-slate-300 px-2 py-1 rounded">ÁMBITO</span>
                                <span class="bg-blue-900/50 text-blue-400 px-2 py-1 rounded">{categoria}</span>
                            </div>
                            <span class="text-slate-500">Hoy</span>
                        </div>
                        <h2 class="text-xl font-bold text-white mb-3 leading-tight">{titulo}</h2>
                        <p class="text-slate-400 text-sm mb-6 flex-grow">{resumen}</p>
                        <a href="{link}" target="_blank" class="text-blue-400 text-sm font-medium hover:text-blue-300 flex justify-end items-center gap-1 mt-auto border-t border-slate-700 pt-4">
                            Leer nota original &rarr;
                        </a>
                    </article>
                    """
        
        # Plantilla HTML intacta con Tailwind
        html_completo = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mercado IA</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ background-color: #0f172a; }}
        .card-bg {{ background-color: #1e293b; }}
    </style>
</head>
<body class="text-slate-300 font-sans antialiased min-h-screen pb-12">
    <nav class="flex justify-between items-center p-6 border-b border-slate-800">
        <div class="text-xl font-bold text-white flex items-center gap-2">Mercado IA 🤖</div>
    </nav>
    <header class="text-center mt-12 mb-10 px-4">
        <h1 class="text-4xl md:text-5xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400 mb-4">El mercado al instante</h1>
        <p class="text-slate-400 max-w-2xl mx-auto">Noticias del mercado de capitales argentino, leídas, analizadas y resumidas por IA en tiempo real.</p>
    </header>
    <main class="max-w-6xl mx-auto px-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {tarjetas_html}
    </main>
</body>
</html>"""
        
        with open("index.html", "w", encoding="utf-8") as archivo:
            archivo.write(html_completo)
            
        print("¡Éxito! Web generada con enlaces reales.")
        
    except Exception as e:
        print("Error con la IA:", e)

else:
    print(f"Error al conectar. Código: {respuesta.status_code}")
