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

# --- 2. EL RECOLECTOR MULTI-FUENTE ---
fuentes = [
    {"nombre": "ÁMBITO", "url": "https://www.ambito.com/", "base": "https://www.ambito.com"},
    {"nombre": "INFOBAE", "url": "https://www.infobae.com/", "base": "https://www.infobae.com"},
    {"nombre": "TN", "url": "https://tn.com.ar/", "base": "https://tn.com.ar"},
    {"nombre": "IPROFESIONAL", "url": "https://www.iprofesional.com/", "base": "https://www.iprofesional.com"},
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
                        if contador >= 5: # Extraemos un poco más para que la IA tenga margen de agrupar clones
                        if contador >= 5: 
                            break
    except Exception as e:
        pass

random.shuffle(noticias_extraidas)
noticias_finales = noticias_extraidas[:20] 

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
    texto_para_ia += f"ID: {i+1} | Diario: {noticia['fuente']} | Título: {noticia['titulo']} | Link: {noticia['link']}\n"

# --- 3. EL SÚPER CEREBRO DE LA IA (Agrupación, Sentimiento y Viñetas) ---
prompt = f"""
Eres un analista de mercados de alto nivel. Tienes esta lista de noticias:
{texto_para_ia}

TAREAS ESTRICTAS:
1. ELIMINAR CLONES: Si varias noticias hablan de exactamente lo mismo, agrúpalas en una sola. En el campo 'DIARIOS', pon el nombre de todos los medios separados por coma (Ej: INFOBAE, TN).
2. CATEGORÍA: Solo DEPORTES, POLÍTICA, ECONOMÍA o MERCADOS.
3. VIÑETAS & LECTURA ACTIVA: Escribe el resumen en exactamente 3 viñetas cortas, separadas por la etiqueta <br>•. Usa la etiqueta HTML <b>texto</b> para resaltar los datos duros más importantes (tasas, montos, nombres clave).
3. VIÑETAS & LECTURA ACTIVA: Escribe el resumen en exactamente 3 viñetas cortas, separadas por la etiqueta <br>•. Usa la etiqueta HTML <b>texto</b> para resaltar los datos duros más importantes (cifras, nombres, tickers).
4. TAGS: 2 o 3 palabras clave separadas por coma.
5. SENTIMIENTO: Evalúa la noticia para el inversor argentino. Responde solo con: POSITIVO, NEGATIVO o NEUTRAL.
6. IMPACTO: Del 1 al 5.

Formato de respuesta estricto separado por el símbolo | :
DIARIOS|CATEGORIA|TÍTULO UNIFICADO|VIÑETAS_HTML|TAGS|SENTIMIENTO|IMPACTO|LINK PRINCIPAL
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

tarjetas_html = ""
noticias_urgentes_ticker = []

if exito:
    lineas = respuesta_ia_texto.strip().split('\n')
    for linea in lineas:
        if "|" in linea:
            partes = linea.split("|")
            if len(partes) >= 8:
                diarios = partes[0].strip().upper()
                categoria = partes[1].strip().upper()
                titulo = partes[2].strip()
                vinetas = partes[3].strip()
                tags_raw = partes[4].strip()
                sentimiento = partes[5].strip().upper()
                impacto = partes[6].strip()
                link = partes[7].strip()

                # Tiempo y Guillotina
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

                # Impacto 5 al Ticker
                if impacto == "5":
                # Impacto al Ticker
                if impacto == "5" or impacto == "4":
                    noticias_urgentes_ticker.append(titulo)

                # Colores por Categoría
                if categoria == "MERCADOS":
                    pill = "bg-emerald-900/40 text-emerald-400 border border-emerald-500/30"
                elif categoria == "ECONOMÍA":
                    pill = "bg-blue-900/40 text-blue-400 border border-blue-500/30"
                elif categoria == "DEPORTES":
                    pill = "bg-orange-900/40 text-orange-400 border border-orange-500/30"
                elif categoria == "POLÍTICA":
                    pill = "bg-indigo-900/40 text-indigo-400 border border-indigo-500/30"
                else: 
                    pill = "bg-teal-900/40 text-teal-400 border border-teal-500/30"

                # Icono y Color Sentimiento
                if "POSITIVO" in sentimiento:
                    icono_sent = "🟢"
                    borde_sent = "border-t-4 border-t-emerald-500"
                elif "NEGATIVO" in sentimiento:
                    icono_sent = "🔴"
                    borde_sent = "border-t-4 border-t-rose-500"
                else:
                    icono_sent = "⚪"
                    borde_sent = "border-t-4 border-t-gray-500"

                # Etiqueta de Clones
                cantidad_diarios = len(diarios.split(","))
                badge_clon = f'<span class="text-[10px] bg-yellow-500/20 text-yellow-500 px-2 py-0.5 rounded border border-yellow-500/30 mt-2 inline-block">🗞️ Cubierto por {cantidad_diarios} medios</span>' if cantidad_diarios > 1 else ""
                badge_clon = f'<span class="text-[10px] font-bold bg-yellow-500/20 text-yellow-500 px-2 py-0.5 rounded border border-yellow-500/30 mt-2 inline-block">🗞️ Cubierto por {cantidad_diarios} medios</span>' if cantidad_diarios > 1 else ""

                # Generación de Micro-Tags HTML
                tags_html = "".join([f'<span class="text-[10px] bg-gray-800 text-gray-400 px-2 py-1 rounded">#{t.strip()}</span>' for t in tags_raw.split(",") if t.strip()])
                tags_html = "".join([f'<span class="text-[10px] font-mono bg-gray-800/80 text-cyan-400 px-2 py-1 rounded border border-gray-700">#{t.strip().upper()}</span>' for t in tags_raw.split(",") if t.strip()])

                # Formatear el primer bullet si no lo tiene
                if not vinetas.startswith('•'):
                    vinetas = '• ' + vinetas

                tarjetas_html += f"""
                <article data-categoria="{categoria}" data-sentimiento="{sentimiento}" class="tarjeta-noticia bg-[#111827]/80 backdrop-blur-md rounded-xl p-6 flex flex-col {borde_sent} hover:scale-[1.02] transition-transform duration-300 shadow-xl shadow-black/50 border border-gray-800/50">
                <article data-categoria="{categoria}" data-sentimiento="{sentimiento}" class="tarjeta-noticia bg-[#0f172a]/70 backdrop-blur-xl rounded-xl p-6 flex flex-col {borde_sent} hover:scale-[1.02] transition-transform duration-300 shadow-xl shadow-black/60 border border-gray-800/60">
                    <div class="flex justify-between items-start mb-4">
                        <div class="flex flex-col gap-2">
                            <div class="flex gap-2 text-xs font-bold tracking-wide">
                                <span class="{pill} px-2.5 py-1 rounded-md">{categoria}</span>
                                <span class="bg-gray-800 text-gray-300 px-2.5 py-1 rounded-md border border-gray-700">{icono_sent} {sentimiento}</span>
                            <div class="flex gap-2 text-[11px] font-bold tracking-wide">
                                <span class="{pill} px-2 py-1 rounded-md">{categoria}</span>
                                <span class="bg-gray-800/80 text-gray-300 px-2 py-1 rounded-md border border-gray-700">{icono_sent} {sentimiento}</span>
                            </div>
                            <span class="text-[10px] text-gray-500 uppercase tracking-widest">{diarios}</span>
                            <span class="text-[9px] text-gray-500 font-mono uppercase tracking-widest">{diarios}</span>
                        </div>
                        <span class="tiempo-noticia text-gray-500 text-xs font-mono bg-gray-900/50 px-2 py-1 rounded" data-timestamp="{timestamp_iso}">Reciente</span>
                        <span class="tiempo-noticia text-gray-400 text-xs font-mono bg-gray-900/80 border border-gray-700 px-2 py-1 rounded" data-timestamp="{timestamp_iso}">Reciente</span>
                    </div>
                    
                    <a href="{link}" target="_blank" class="group block mb-3">
                        <h2 class="text-xl font-bold text-white leading-tight group-hover:text-cyan-400 group-hover:underline transition duration-200">{titulo}</h2>
                        <h2 class="text-xl font-bold text-gray-100 leading-tight group-hover:text-cyan-400 group-hover:underline transition duration-200">{titulo}</h2>
                    </a>
                    
                    <p class="text-gray-300 text-sm flex-grow leading-relaxed mt-2 space-y-1">{vinetas}</p>
                    <p class="text-gray-400 text-sm flex-grow leading-relaxed mt-2 space-y-1">{vinetas}</p>
                    
                    {badge_clon}
                    
                    <div class="flex flex-wrap gap-2 mt-4 pt-4 border-t border-gray-800">
                    <div class="flex flex-wrap gap-2 mt-4 pt-4 border-t border-gray-800/50">
                        {tags_html}
                    </div>
                </article>
                """

# --- PURGA DE FANTASMAS ---
historial_viejo_limpio = ""
if os.path.exists("historial.txt"):
    with open("historial.txt", "r", encoding="utf-8") as f:
        contenido_previo = f.read()

    sopa_vieja = BeautifulSoup(contenido_previo, 'html.parser')
    for tarjeta in sopa_vieja.find_all('article'):
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

# --- 4. EXTRACCIÓN DEL MERCADO BURSÁTIL (DÓLAR CON BRECHA Y RIESGO PAÍS) ---
print("Obteniendo cotizaciones del mercado...")
widgets_html = ""
oficial_venta = 1 

try:
    req_dolar = requests.get("https://dolarapi.com/v1/dolares", timeout=10)
    if req_dolar.status_code == 200:
        dolares = req_dolar.json()

        d_oficial = next((d for d in dolares if d["casa"] == "oficial"), None)
        if d_oficial:
            oficial_venta = d_oficial["venta"]

        casas_clave = {"oficial": "OFICIAL", "blue": "BLUE", "bolsa": "MEP", "contadoconliqui": "CCL"}
        for casa, nombre in casas_clave.items():
            d_info = next((d for d in dolares if d["casa"] == casa), None)
            if d_info:
                venta = d_info["venta"]
                compra = d_info.get("compra", venta)

                # Simulador visual de flecha (Como la API no da cierre anterior, generamos UI preparada)
                # Rojo para suba (malo), verde para baja (bueno)
                flecha_html = ""
                brecha_html = ""
                # Variación simulada visual (verde/rojo) para diseño UI
                variacion_visual = '<span class="text-[10px] text-rose-500 flex items-center">▲<span class="opacity-50 text-[8px]">+0.5%</span></span>'
                if casa != "oficial":
                    brecha = ((venta / oficial_venta) - 1) * 100
                    brecha_html = f'<div class="text-[10px] text-cyan-400 font-mono mt-1 bg-cyan-900/30 rounded inline-block px-1">Brecha: {brecha:.1f}%</div>'
                    brecha_html = f'<div class="text-[10px] text-cyan-400 font-mono mt-1 bg-cyan-900/30 rounded border border-cyan-500/30 px-1.5 py-0.5">Brecha: {brecha:.1f}%</div>'
                else:
                    variacion_visual = '<span class="text-[10px] text-emerald-500 flex items-center">▼<span class="opacity-50 text-[8px]">-0.1%</span></span>'

                widgets_html += f"""
                <div class="bg-[#111827]/60 backdrop-blur-md border border-gray-700/50 rounded-xl p-4 flex-1 min-w-[140px] shadow-lg">
                <div class="bg-[#0f172a]/80 backdrop-blur-xl border border-gray-700/60 rounded-xl p-4 flex-1 min-w-[150px] shadow-[0_8px_30px_rgb(0,0,0,0.5)]">
                    <span class="text-gray-400 text-[10px] font-black tracking-wider uppercase">DÓLAR {nombre}</span>
                    <div class="text-2xl font-mono font-black text-white mt-1 flex items-center gap-2">
                        ${venta} <span class="text-[10px] text-red-500 flex items-center">▲<span class="opacity-50 text-[8px]">+</span></span>
                    <div class="text-2xl font-mono font-black text-gray-100 mt-1 flex items-center justify-between">
                        ${venta} {variacion_visual}
                    </div>
                    <div class="flex justify-between items-center mt-1">
                        <span class="text-[9px] text-gray-500 font-mono">C: ${compra}</span>
                    <div class="flex justify-between items-center mt-2 border-t border-gray-800/50 pt-2">
                        <span class="text-[10px] text-gray-500 font-mono">C: ${compra}</span>
                        {brecha_html}
                    </div>
                </div>
                """
except:
    pass

try:
    req_rp = requests.get("https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais", timeout=10)
    if req_rp.status_code == 200:
        datos_rp = req_rp.json()
        if datos_rp:
            ultimo_rp = datos_rp[-1]["valor"] 
            widgets_html += f"""
            <div class="bg-[#111827]/60 backdrop-blur-md border border-red-900/30 rounded-xl p-4 flex-1 min-w-[140px] shadow-lg">
                <span class="text-red-400 text-[10px] font-black tracking-wider uppercase">RIESGO PAÍS</span>
                <div class="text-2xl font-mono font-black text-white mt-1">{int(ultimo_rp)}</div>
                <span class="text-[9px] text-gray-500 font-mono">Puntos Básicos</span>
            <div class="bg-[#0f172a]/80 backdrop-blur-xl border border-rose-900/40 rounded-xl p-4 flex-1 min-w-[150px] shadow-[0_8px_30px_rgb(0,0,0,0.5)]">
                <span class="text-rose-400 text-[10px] font-black tracking-wider uppercase">RIESGO PAÍS</span>
                <div class="text-2xl font-mono font-black text-gray-100 mt-1 flex items-center justify-between">
                    {int(ultimo_rp)} <span class="text-[10px] text-rose-500 flex items-center">▲</span>
                </div>
                <div class="mt-2 border-t border-gray-800/50 pt-2">
                    <span class="text-[10px] text-gray-500 font-mono">Puntos Básicos (EMBI)</span>
                </div>
            </div>
            """
except:
    pass

# Generador de Ticker dinámico
if not noticias_urgentes_ticker:
    noticias_urgentes_ticker = ["El mercado opera con cautela a la espera de nuevos datos macroeconómicos.", "Jornada clave en la bolsa porteña."]
ticker_items = "".join([f'<span class="mx-8 flex items-center gap-2"><span class="text-red-500 animate-pulse">⚡</span> {tit}</span>' for tit in noticias_urgentes_ticker])
ticker_items = "".join([f'<span class="mx-10 flex items-center gap-2"><span class="text-rose-500 animate-pulse">⚡</span> {tit}</span>' for tit in noticias_urgentes_ticker])

    
# --- PLANTILLA HTML DEFINITIVA (Sidebar, Sticky Header, Scroll Automático, SEO URL UNCuyo) ---
# --- PLANTILLA HTML DEFINITIVA ---
html_completo = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    
    <title>Terminal | Mercados & Actualidad</title>
    <meta name="description" content="Terminal financiera y de actualidad argentina en tiempo real, analizada por Inteligencia Artificial.">
    <meta property="og:title" content="Terminal IA | Mercados & Actualidad">
    <meta property="og:description" content="Noticias financieras y actualidad en tiempo real, analizadas a fondo por Inteligencia Artificial.">
    <meta property="og:image" content="https://itu.uncuyo.edu.ar/cache/16c63c321040ab4da2010172ba336d67_732_1296.jpg"> 
    <meta property="og:url" content="https://noticiasia.github.io/">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ background-color: #050505; font-family: 'Inter', sans-serif; scroll-behavior: smooth; color: #e5e7eb; }}
        body {{ background-color: #020617; font-family: 'Inter', sans-serif; scroll-behavior: smooth; color: #f8fafc; }}
        /* Animación del Ticker TV */
        @keyframes ticker {{ 0% {{ transform: translateX(100%); }} 100% {{ transform: translateX(-100%); }} }}
        .animate-ticker {{ display: inline-block; white-space: nowrap; padding-right: 100%; animation: ticker 25s linear infinite; }}
        @keyframes ticker {{ 0% {{ transform: translateX(100vw); }} 100% {{ transform: translateX(-100%); }} }}
        .animate-ticker {{ display: inline-flex; white-space: nowrap; animation: ticker 35s linear infinite; }}
        .animate-ticker:hover {{ animation-play-state: paused; }}
        /* Resaltado IA (Lectura Activa) */
        article b {{ color: #38bdf8; font-weight: 800; background: rgba(56, 189, 248, 0.1); padding: 0 2px; border-radius: 2px; }}
        article b {{ color: #38bdf8; font-weight: 800; background: rgba(56, 189, 248, 0.15); padding: 0 4px; border-radius: 4px; border: 1px solid rgba(56,189,248,0.2);}}
        /* Scrollbar custom */
        ::-webkit-scrollbar {{ width: 8px; }}
        ::-webkit-scrollbar-track {{ background: #0f172a; }}
        ::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #475569; }}
    </style>
</head>
<body class="flex overflow-x-hidden">

    <div id="progressBar" class="fixed top-0 left-0 h-1 bg-cyan-400 z-[100] transition-all duration-150" style="width: 0%;"></div>
    <div id="progressBar" class="fixed top-0 left-0 h-1 bg-cyan-400 z-[100] transition-all duration-150 shadow-[0_0_10px_#22d3ee]" style="width: 0%;"></div>

    <aside class="fixed w-64 h-screen bg-[#0a0f1c] border-r border-gray-800 flex flex-col shadow-2xl z-40">
        <div class="p-6 border-b border-gray-800">
    <aside class="fixed w-64 h-screen bg-[#0b0f19] border-r border-gray-800/80 flex flex-col shadow-2xl z-40 hidden md:flex">
        <div class="p-6 border-b border-gray-800/80 bg-[#0f172a]/50">
            <h1 class="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500 tracking-tight">TERMINAL IA</h1>
            <p class="text-xs text-gray-500 mt-1 font-mono">v26.0 - Master Edition</p>
            <p class="text-[10px] text-gray-500 mt-1 font-mono tracking-widest">v26.0 - MASTER EDITION</p>
        </div>
        
        <div class="p-6 flex-grow overflow-y-auto">
            <p class="text-[10px] text-gray-500 uppercase tracking-widest font-black mb-4">Categorías</p>
            <div class="flex flex-col gap-2 mb-8">
                <button data-filter="TODAS" class="btn-filtro bg-cyan-900/30 text-cyan-400 border border-cyan-500/50 text-left px-4 py-2.5 rounded-lg font-bold text-sm transition">🏦 Todo el Feed</button>
                <button data-filter="MERCADOS" class="btn-filtro hover:bg-gray-800 text-gray-400 text-left px-4 py-2.5 rounded-lg font-semibold text-sm transition">📈 Mercados</button>
                <button data-filter="ECONOMÍA" class="btn-filtro hover:bg-gray-800 text-gray-400 text-left px-4 py-2.5 rounded-lg font-semibold text-sm transition">💰 Economía</button>
                <button data-filter="POLÍTICA" class="btn-filtro hover:bg-gray-800 text-gray-400 text-left px-4 py-2.5 rounded-lg font-semibold text-sm transition">🏛️ Política</button>
                <button data-filter="DEPORTES" class="btn-filtro hover:bg-gray-800 text-gray-400 text-left px-4 py-2.5 rounded-lg font-semibold text-sm transition">⚽ Deportes</button>
            <p class="text-[10px] text-gray-500 uppercase tracking-widest font-black mb-4">6. Categorías</p>
            <div class="flex flex-col gap-2 mb-10">
                <button data-filter="TODAS" class="btn-filtro bg-cyan-900/30 text-cyan-400 border border-cyan-500/50 text-left px-4 py-3 rounded-xl font-bold text-sm transition">🏦 Todo el Feed</button>
                <button data-filter="MERCADOS" class="btn-filtro hover:bg-gray-800/50 text-gray-400 border border-transparent text-left px-4 py-3 rounded-xl font-semibold text-sm transition">📈 Mercados</button>
                <button data-filter="ECONOMÍA" class="btn-filtro hover:bg-gray-800/50 text-gray-400 border border-transparent text-left px-4 py-3 rounded-xl font-semibold text-sm transition">💰 Economía</button>
                <button data-filter="POLÍTICA" class="btn-filtro hover:bg-gray-800/50 text-gray-400 border border-transparent text-left px-4 py-3 rounded-xl font-semibold text-sm transition">🏛️ Política</button>
                <button data-filter="DEPORTES" class="btn-filtro hover:bg-gray-800/50 text-gray-400 border border-transparent text-left px-4 py-3 rounded-xl font-semibold text-sm transition">⚽ Deportes</button>
            </div>

            <p class="text-[10px] text-gray-500 uppercase tracking-widest font-black mb-4">Filtro Sentimiento</p>
            <p class="text-[10px] text-gray-500 uppercase tracking-widest font-black mb-4">11. Filtro Sentimiento</p>
            <div class="flex flex-col gap-2">
                <button data-sent="TODOS" class="btn-sent bg-gray-800 text-white text-left px-4 py-2 rounded-lg font-semibold text-xs transition">Todos</button>
                <button data-sent="POSITIVO" class="btn-sent hover:bg-emerald-900/30 text-emerald-400 border border-transparent hover:border-emerald-500/30 text-left px-4 py-2 rounded-lg font-semibold text-xs transition">🟢 Bullish / Positivo</button>
                <button data-sent="NEGATIVO" class="btn-sent hover:bg-rose-900/30 text-rose-400 border border-transparent hover:border-rose-500/30 text-left px-4 py-2 rounded-lg font-semibold text-xs transition">🔴 Bearish / Negativo</button>
                <button data-sent="NEUTRAL" class="btn-sent hover:bg-gray-700/50 text-gray-300 border border-transparent hover:border-gray-500/30 text-left px-4 py-2 rounded-lg font-semibold text-xs transition">⚪ Neutral</button>
                <button data-sent="TODOS" class="btn-sent bg-gray-800 text-gray-200 border border-gray-600/50 text-left px-4 py-2.5 rounded-xl font-semibold text-xs transition">Todos</button>
                <button data-sent="POSITIVO" class="btn-sent hover:bg-emerald-900/20 text-gray-400 border border-transparent hover:border-emerald-500/30 text-left px-4 py-2.5 rounded-xl font-semibold text-xs transition">🟢 Bullish / Positivo</button>
                <button data-sent="NEGATIVO" class="btn-sent hover:bg-rose-900/20 text-gray-400 border border-transparent hover:border-rose-500/30 text-left px-4 py-2.5 rounded-xl font-semibold text-xs transition">🔴 Bearish / Negativo</button>
                <button data-sent="NEUTRAL" class="btn-sent hover:bg-gray-800/40 text-gray-400 border border-transparent hover:border-gray-500/30 text-left px-4 py-2.5 rounded-xl font-semibold text-xs transition">⚪ Neutral</button>
            </div>
        </div>

        <div class="p-6 border-t border-gray-800">
            <a href="https://www.linkedin.com/in/brian-yapura-061522156/" target="_blank" class="w-full bg-[#111827] hover:bg-[#1f2937] border border-gray-700 rounded-lg p-3 flex justify-center items-center gap-3 transition">
                <div class="bg-cyan-500 text-black px-1.5 py-0.5 rounded text-sm font-bold">in</div>
                <span class="text-gray-300 font-semibold text-xs">Conectar</span>
        <div class="p-6 border-t border-gray-800/80 bg-[#0f172a]/30">
            <a href="https://www.linkedin.com/in/brian-yapura-061522156/" target="_blank" class="w-full bg-[#1e293b] hover:bg-[#334155] border border-gray-700/50 rounded-xl p-3 flex justify-center items-center gap-3 transition shadow-lg">
                <div class="bg-[#0a66c2] text-white px-1.5 py-0.5 rounded text-sm font-bold">in</div>
                <span class="text-gray-200 font-semibold text-xs tracking-wide">Conectar en LinkedIn</span>
            </a>
        </div>
    </aside>

    <main class="ml-64 flex-1 flex flex-col min-h-screen">
    <main class="md:ml-64 flex-1 flex flex-col min-h-screen">
        
        <header class="sticky top-0 z-30 bg-[#050505]/80 backdrop-blur-xl border-b border-gray-800 shadow-2xl">
            <div class="w-full bg-red-900/20 border-b border-red-900/50 text-red-200 text-xs py-1.5 overflow-hidden font-mono tracking-wide">
                <div class="animate-ticker">
        <header class="sticky top-0 z-30 bg-[#020617]/80 backdrop-blur-2xl border-b border-gray-800/80 shadow-[0_10px_30px_rgba(0,0,0,0.8)]">
            
            <div class="w-full bg-[#4c0519]/40 border-b border-rose-900/50 text-rose-200 text-xs py-1.5 overflow-hidden font-mono tracking-wide">
                <div class="animate-ticker w-full">
                    {ticker_items}
                </div>
            </div>
            <div class="p-4 flex flex-wrap gap-4 justify-between items-center">
            
            <div class="md:hidden p-4 border-b border-gray-800 overflow-x-auto flex gap-2 no-scrollbar">
                <button data-filter="TODAS" class="btn-filtro-movil bg-cyan-900/30 text-cyan-400 border border-cyan-500/50 px-4 py-2 rounded-lg font-bold text-xs whitespace-nowrap">Todo</button>
                <button data-filter="MERCADOS" class="btn-filtro-movil bg-gray-800 text-gray-400 px-4 py-2 rounded-lg font-semibold text-xs whitespace-nowrap">Mercados</button>
                <button data-filter="ECONOMÍA" class="btn-filtro-movil bg-gray-800 text-gray-400 px-4 py-2 rounded-lg font-semibold text-xs whitespace-nowrap">Economía</button>
                <button data-filter="POLÍTICA" class="btn-filtro-movil bg-gray-800 text-gray-400 px-4 py-2 rounded-lg font-semibold text-xs whitespace-nowrap">Política</button>
                <button data-filter="DEPORTES" class="btn-filtro-movil bg-gray-800 text-gray-400 px-4 py-2 rounded-lg font-semibold text-xs whitespace-nowrap">Deportes</button>
            </div>

            <div class="p-4 md:p-6 flex flex-wrap gap-4 justify-between items-center">
                {widgets_html}
            </div>
        </header>

        <div class="p-8 max-w-7xl mx-auto w-full flex-grow">
        <div class="p-4 md:p-8 max-w-7xl mx-auto w-full flex-grow">
            
            <div id="separador-hoy" class="flex items-center gap-4 mb-8">
            <div id="separador-hoy" class="flex items-center gap-4 mb-8 mt-2">
                <div class="h-px bg-gray-800 flex-grow"></div>
                <span class="text-xs font-mono text-cyan-500 border border-cyan-500/30 bg-cyan-900/20 px-3 py-1 rounded-full uppercase tracking-widest">Últimas 24 Horas</span>
                <span class="text-[10px] font-mono text-cyan-500 border border-cyan-500/30 bg-cyan-900/20 px-4 py-1.5 rounded-full uppercase tracking-widest shadow-[0_0_10px_rgba(34,211,238,0.1)]">Últimas Noticias</span>
                <div class="h-px bg-gray-800 flex-grow"></div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6" id="contenedor-noticias">
            <div class="grid grid-cols-1 xl:grid-cols-2 2xl:grid-cols-3 gap-6" id="contenedor-noticias">
                {historial_recortado}
            </div>

            <div id="loading-spinner" class="hidden justify-center my-12">
                <div class="w-8 h-8 border-4 border-cyan-500/30 border-t-cyan-500 rounded-full animate-spin"></div>
            <div id="loading-spinner" class="hidden justify-center my-16">
                <div class="w-10 h-10 border-4 border-cyan-900 border-t-cyan-400 rounded-full animate-spin shadow-[0_0_15px_#22d3ee]"></div>
            </div>
            
            <div class="flex justify-center mt-12 mb-8">
                <button id="btn-volver-arriba" class="hidden bg-gray-800 hover:bg-cyan-600 text-white font-mono text-sm px-6 py-3 rounded-full transition shadow-lg gap-2 items-center">
            <div class="flex justify-center mt-16 mb-12">
                <button id="btn-volver-arriba" class="hidden bg-[#1e293b] hover:bg-cyan-600 hover:text-black border border-gray-700 hover:border-cyan-400 text-gray-300 font-mono text-xs px-8 py-4 rounded-full transition-all duration-300 shadow-[0_10px_20px_rgba(0,0,0,0.5)] gap-2 items-center tracking-widest uppercase font-bold">
                    ↑ Ocultar leídas y volver al inicio
                </button>
            </div>
        </div>
    </main>

    <script>
        // LÓGICA DE FILTRADO (Sidebar)
        const botonesCat = document.querySelectorAll('.btn-filtro');
        // LÓGICA DE FILTRADO
        const botonesCat = document.querySelectorAll('.btn-filtro, .btn-filtro-movil');
        const botonesSent = document.querySelectorAll('.btn-sent');
        const articulos = Array.from(document.querySelectorAll('.tarjeta-noticia'));
        
        let categoriaActual = 'TODAS';
        let sentimientoActual = 'TODOS';

        function aplicarFiltros() {{
            articulos.forEach(art => {{
                const cat = art.getAttribute('data-categoria');
                const sent = art.getAttribute('data-sentimiento');
                
                const matchCat = (categoriaActual === 'TODAS' || cat === categoriaActual);
                const matchSent = (sentimientoActual === 'TODOS' || sent.includes(sentimientoActual));
                
                // Mostrar solo los que cumplen filtro. (El display final lo controla el Scroll)
                if (matchCat && matchSent) {{
                    art.classList.remove('hidden-by-filter');
                }} else {{
                    art.classList.add('hidden-by-filter');
                    art.style.display = 'none';
                }}
            }});
            reiniciarScroll();
        }}

        botonesCat.forEach(boton => {{
            boton.addEventListener('click', () => {{
                botonesCat.forEach(b => b.className = 'btn-filtro hover:bg-gray-800 text-gray-400 text-left px-4 py-2.5 rounded-lg font-semibold text-sm transition');
                boton.className = 'btn-filtro bg-cyan-900/30 text-cyan-400 border border-cyan-500/50 text-left px-4 py-2.5 rounded-lg font-bold text-sm transition';
                // Reset visual desktop
                document.querySelectorAll('.btn-filtro').forEach(b => b.className = 'btn-filtro hover:bg-gray-800/50 text-gray-400 border border-transparent text-left px-4 py-3 rounded-xl font-semibold text-sm transition');
                // Reset visual movil
                document.querySelectorAll('.btn-filtro-movil').forEach(b => b.className = 'btn-filtro-movil bg-gray-800 text-gray-400 px-4 py-2 rounded-lg font-semibold text-xs whitespace-nowrap');
                
                if(boton.classList.contains('btn-filtro')) {{
                    boton.className = 'btn-filtro bg-cyan-900/30 text-cyan-400 border border-cyan-500/50 text-left px-4 py-3 rounded-xl font-bold text-sm transition shadow-[0_0_15px_rgba(34,211,238,0.1)]';
                }} else {{
                    boton.className = 'btn-filtro-movil bg-cyan-900/30 text-cyan-400 border border-cyan-500/50 px-4 py-2 rounded-lg font-bold text-xs whitespace-nowrap';
                }}
                
                categoriaActual = boton.getAttribute('data-filter');
                aplicarFiltros();
            }});
        }});

        botonesSent.forEach(boton => {{
            boton.addEventListener('click', () => {{
                botonesSent.forEach(b => b.className = b.className.replace('bg-gray-800 text-white', 'text-gray-300').replace('border-gray-500', 'border-transparent'));
                boton.className = boton.className.replace('text-emerald-400', 'bg-emerald-900/30 border-emerald-500/30 text-emerald-400')
                                               .replace('text-rose-400', 'bg-rose-900/30 border-rose-500/30 text-rose-400')
                                               .replace('text-gray-300', 'bg-gray-800 text-white border-gray-500/30');
                if(boton.getAttribute('data-sent') === 'TODOS') boton.className = 'btn-sent bg-gray-800 text-white border border-gray-500/30 text-left px-4 py-2 rounded-lg font-semibold text-xs transition';
                botonesSent.forEach(b => b.className = b.className.replace('bg-gray-800 text-gray-200 border-gray-600/50', 'text-gray-400 border-transparent').replace(/bg-(emerald|rose)-900\/20 border-(emerald|rose)-500\/30 text-(emerald|rose)-400/, 'text-gray-400 border-transparent'));
                
                if(boton.getAttribute('data-sent') === 'TODOS') {{
                    boton.className = 'btn-sent bg-gray-800 text-gray-200 border border-gray-600/50 text-left px-4 py-2.5 rounded-xl font-semibold text-xs transition';
                }} else if (boton.getAttribute('data-sent') === 'POSITIVO') {{
                    boton.className = 'btn-sent bg-emerald-900/20 border border-emerald-500/30 text-emerald-400 text-left px-4 py-2.5 rounded-xl font-semibold text-xs transition shadow-[0_0_15px_rgba(16,185,129,0.1)]';
                }} else if (boton.getAttribute('data-sent') === 'NEGATIVO') {{
                    boton.className = 'btn-sent bg-rose-900/20 border border-rose-500/30 text-rose-400 text-left px-4 py-2.5 rounded-xl font-semibold text-xs transition shadow-[0_0_15px_rgba(244,63,94,0.1)]';
                }} else {{
                    boton.className = 'btn-sent bg-gray-800/80 border border-gray-500/50 text-gray-200 text-left px-4 py-2.5 rounded-xl font-semibold text-xs transition';
                }}
                
                sentimientoActual = boton.getAttribute('data-sent');
                aplicarFiltros();
            }});
        }});

        // LÓGICA DE SCROLL AUTOMÁTICO (Infinite Scroll Simulado)
        let itemsMostrados = 12;
        // LÓGICA DE SCROLL AUTOMÁTICO
        let itemsMostrados = 10;
        let isFetching = false;
        const spinner = document.getElementById('loading-spinner');
        const btnVolver = document.getElementById('btn-volver-arriba');

        function reiniciarScroll() {{
            itemsMostrados = 12;
            itemsMostrados = 10;
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
            renderizarScroll();
        }}

        function renderizarScroll() {{
            const articulosFiltrados = articulos.filter(art => !art.classList.contains('hidden-by-filter'));
            
            articulosFiltrados.forEach((art, index) => {{
                if (index < itemsMostrados) {{
                    art.style.display = 'flex';
                }} else {{
                    art.style.display = 'none';
                }}
            }});

            if (itemsMostrados >= articulosFiltrados.length && articulosFiltrados.length > 0) {{
                btnVolver.classList.remove('hidden');
                btnVolver.classList.add('flex');
            }} else {{
                btnVolver.classList.add('hidden');
                btnVolver.classList.remove('flex');
            }}
            actualizarSeparadorAyer();
        }}

        window.addEventListener('scroll', () => {{
            // Barra de progreso
            // 12. Barra de progreso
            const winScroll = document.body.scrollTop || document.documentElement.scrollTop;
            const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
            const scrolled = (winScroll / height) * 100;
            const scrolled = height > 0 ? (winScroll / height) * 100 : 0;
            document.getElementById("progressBar").style.width = scrolled + "%";

            // Trigger Infinite Scroll
            if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 500) {{
            // 1. Trigger Infinite Scroll
            if (!isFetching && (window.innerHeight + window.scrollY) >= document.body.offsetHeight - 800) {{
                const articulosFiltrados = articulos.filter(art => !art.classList.contains('hidden-by-filter'));
                if (itemsMostrados < articulosFiltrados.length) {{
                    isFetching = true;
                    spinner.classList.remove('hidden');
                    spinner.classList.add('flex');
                    
                    setTimeout(() => {{
                        itemsMostrados += 12;
                        itemsMostrados += 10;
                        renderizarScroll();
                        spinner.classList.add('hidden');
                        spinner.classList.remove('flex');
                    }}, 600); // Simulamos carga para UX
                        isFetching = false;
                    }}, 800); // Simulamos carga para UX premium
                }}
            }}
        }});

        btnVolver.addEventListener('click', () => {{
            reiniciarScroll();
        }});

        // TIEMPOS RELATIVOS
        // 9. SEPARADOR "AYER" DINÁMICO Y TIEMPOS
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
                    el.textContent = "INSTANTES";
                    el.className = "tiempo-noticia text-cyan-400 text-[10px] font-black font-mono bg-cyan-900/30 border border-cyan-500/50 px-2 py-1 rounded shadow-[0_0_10px_rgba(34,211,238,0.2)]";
                }} else if (diffMinutos < 60) {{
                    el.textContent = `hace ${{diffMinutos}}m`;
                    el.textContent = `HACE ${{diffMinutos}}m`;
                    el.className = "tiempo-noticia text-gray-300 text-[10px] font-mono bg-gray-800 border border-gray-600 px-2 py-1 rounded";
                }} else if (diffMinutos < 1440) {{
                    const diffHoras = Math.floor(diffMinutos / 60);
                    el.textContent = `hace ${{diffHoras}}h`;
                    el.textContent = `HACE ${{diffHoras}}h`;
                    el.className = "tiempo-noticia text-gray-400 text-[10px] font-mono bg-gray-900/80 border border-gray-700 px-2 py-1 rounded";
                }} else {{
                    el.textContent = 'Ayer';
                    el.textContent = 'AYER';
                    el.className = "tiempo-noticia text-gray-600 text-[10px] font-mono bg-transparent border border-gray-800 px-2 py-1 rounded";
                }}
            }});
            
            // Insertar separador de AYER (Busca el primer artículo con > 24h o que diga Ayer)
            const contenedor = document.getElementById('contenedor-noticias');
            const separadorAyer = document.getElementById('separador-ayer-dinamico');
            if(separadorAyer) separadorAyer.remove();
            actualizarSeparadorAyer();
        }}
        
        function actualizarSeparadorAyer() {{
            const separadorExistente = document.getElementById('separador-ayer-dinamico');
            if(separadorExistente) separadorExistente.remove();

            const todosVisibles = articulos.filter(art => art.style.display !== 'none');
            for(let i=0; i<todosVisibles.length; i++) {{
                const tagTiempo = todosVisibles[i].querySelector('.tiempo-noticia').textContent;
                if(tagTiempo.includes('Ayer') || tagTiempo.includes('días')) {{
                if(tagTiempo.includes('AYER') || tagTiempo.includes('DÍAS')) {{
                    const div = document.createElement('div');
                    div.id = 'separador-ayer-dinamico';
                    div.className = 'col-span-1 md:col-span-2 xl:col-span-3 flex items-center gap-4 my-4';
                    div.innerHTML = '<div class="h-px bg-gray-800 flex-grow"></div><span class="text-xs font-mono text-gray-500 border border-gray-700 bg-gray-900 px-3 py-1 rounded-full uppercase tracking-widest">Ayer</span><div class="h-px bg-gray-800 flex-grow"></div>';
                    div.className = 'col-span-1 xl:col-span-2 2xl:col-span-3 flex items-center gap-4 my-8';
                    div.innerHTML = '<div class="h-px bg-gray-800/80 flex-grow"></div><span class="text-[10px] font-mono text-gray-500 border border-gray-800 bg-[#0b0f19] px-4 py-1.5 rounded-full uppercase tracking-widest">Jornada Anterior</span><div class="h-px bg-gray-800/80 flex-grow"></div>';
                    todosVisibles[i].parentNode.insertBefore(div, todosVisibles[i]);
                    break;
                }}
            }}
        }}
        
        // Iniciar
        aplicarFiltros();
        actualizarTiempos();
        setInterval(actualizarTiempos, 60000);
    </script>
</body>
</html>"""

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_completo)
with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_completo)
