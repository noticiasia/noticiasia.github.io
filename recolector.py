import json
import os
import random
import time
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup
from google import genai

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
                        if contador >= 12: 
                            break
    except Exception:
        pass

random.shuffle(noticias_extraidas)
noticias_finales = noticias_extraidas[:40] 

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
        except Exception:
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
    except Exception:
        pass

texto_para_ia = ""
for i, noticia in enumerate(noticias_finales):
    texto_para_ia += f"ID: {i+1} | Diario: {noticia['fuente']} | Título: {noticia['titulo']} | Link: {noticia['link']}\n"

# --- 3. EL SÚPER CEREBRO DE LA IA ---
prompt = f"""
Eres un analista de mercados de alto nivel. Tienes esta lista de noticias:
{texto_para_ia}

TAREAS ESTRICTAS:
1. ELIMINAR CLONES: Si varias noticias hablan de exactamente lo mismo, agrúpalas en una sola. En el campo 'DIARIOS', pon el nombre de todos los medios separados por coma (Ej: INFOBAE, TN).
2. CATEGORÍA: Solo DEPORTES, POLÍTICA, ECONOMÍA o MERCADOS.
3. VIÑETAS & LECTURA ACTIVA: Escribe el resumen en exactamente 3 viñetas cortas, separadas por la etiqueta <br><span class="text-[#00E5FF] font-bold mr-2">▪</span>. Usa la etiqueta HTML <b>texto</b> para resaltar los datos duros más importantes (cifras, nombres).
4. CONTEXTO DE IMPACTO: En la tercera y última viñeta, argumenta de forma obligatoria el porqué de la calificación de impacto asignada (ej. "Impacto negativo porque devalúa la moneda...").
5. TAGS: 2 o 3 palabras clave separadas por coma.
6. SENTIMIENTO: Evalúa la noticia para el inversor argentino. Responde solo con: POSITIVO, NEGATIVO o NEUTRAL.
7. IMPACTO: Del 1 al 5.
8. BLINDAJE DE LINK: En el campo de LINK PRINCIPAL, debes devolver EXACTAMENTE la URL que se te entregó en la lista, sin modificar, cortar, ni inventar nada.

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
    except Exception:
        time.sleep(10)

if not exito:
    try:
        respuesta_ia = client.models.generate_content(model='gemini-1.5-flash', contents=prompt)
        respuesta_ia_texto = respuesta_ia.text
        exito = True
    except Exception:
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
                
                if diarios == "DIARIOS" or "DIARIOS|" in linea or "DIARIO" in diarios:
                    continue
                    
                categoria = partes[1].strip().upper()
                titulo = partes[2].strip()
                vinetas = partes[3].strip()
                tags_raw = partes[4].strip()
                sentimiento = partes[5].strip().upper()
                impacto = partes[6].strip()
                link = partes[7].strip()

                timestamp_iso = tiempos_reales.get(link, datetime.now(timezone.utc).isoformat())
                try:
                    dt_noticia = datetime.fromisoformat(timestamp_iso.replace('Z', '+00:00'))
                    if dt_noticia.tzinfo is None:
                        dt_noticia = dt_noticia.replace(tzinfo=timezone.utc)
                    diferencia_horas = (datetime.now(timezone.utc) - dt_noticia).total_seconds() / 3600
                    if diferencia_horas > 48:
                        continue 
                except Exception:
                    pass

                if impacto in ["5", "4"]:
                    noticias_urgentes_ticker.append(titulo)

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

                if "POSITIVO" in sentimiento:
                    icono_sent = "🟢"
                    borde_sent = "border-t-4 border-t-emerald-500"
                elif "NEGATIVO" in sentimiento:
                    icono_sent = "🔴"
                    borde_sent = "border-t-4 border-t-rose-500"
                else:
                    icono_sent = "⚪"
                    borde_sent = "border-t-4 border-t-gray-500"

                cantidad_diarios = len(diarios.split(","))
                badge_clon = f'<span class="text-[10px] font-bold bg-yellow-500/20 text-yellow-500 px-2 py-0.5 rounded border border-yellow-500/30 mt-2 inline-block">🗞️ Cubierto por {cantidad_diarios} medios</span>' if cantidad_diarios > 1 else ""

                tags_html = "".join([f'<span class="text-[10px] font-mono bg-gray-800/80 text-[#00E5FF] px-2 py-1 rounded border border-gray-700">#{t.strip().upper()}</span>' for t in tags_raw.split(",") if t.strip()])

                vinetas = vinetas.replace('- <span', '<span').replace('- ▪', '▪').replace('• <span', '<span')
                if not vinetas.startswith('<span'):
                    vinetas = '<span class="text-[#00E5FF] font-bold mr-2">▪</span>' + vinetas
                vinetas = vinetas.replace('<br>•', '<br><span class="text-[#00E5FF] font-bold mr-2">▪</span>').replace('<br>-', '<br><span class="text-[#00E5FF] font-bold mr-2">▪</span>')

                tarjetas_html += f"""
                <article data-categoria="{categoria}" data-impacto="{impacto}" data-url="{link}" class="tarjeta-noticia bg-[#0f172a]/70 backdrop-blur-xl border border-white/10 hover:border-[#00E5FF]/50 transition-all duration-300 shadow-[0_8px_30px_rgb(0,0,0,0.3)] rounded-xl p-6 flex flex-col {borde_sent} h-[380px] overflow-hidden relative">
                    <div class="flex justify-between items-start mb-3 shrink-0 select-none">
                        <div class="flex flex-col gap-2 max-w-[70%]">
                            <div class="flex flex-wrap gap-2 text-[11px] font-bold tracking-wide">
                                <span class="{pill} px-2 py-1 rounded-md whitespace-nowrap">{categoria}</span>
                                <span class="bg-[#1A1A1A]/80 text-gray-300 px-2 py-1 rounded-md border border-[#2A2A2A] whitespace-nowrap">{icono_sent} {sentimiento}</span>
                            </div>
                            <span class="text-sm text-[#00E5FF] font-black font-mono tracking-wide uppercase break-words">{diarios}</span>
                        </div>
                        <div class="flex flex-col items-end gap-2 shrink-0 z-10">
                            <button class="btn-guardar text-xl opacity-50 hover:opacity-100 hover:scale-110 transition-all cursor-pointer" data-url="{link}" title="Guardar noticia">🔖</button>
                            <span class="tiempo-noticia text-gray-400 text-[10px] font-mono bg-[#1A1A1A]/80 border border-[#2A2A2A] px-2 py-1 rounded" data-timestamp="{timestamp_iso}"></span>
                            <span class="badge-leida hidden text-[9px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30 px-1.5 py-0.5 rounded tracking-widest uppercase">LEÍDA</span>
                        </div>
                    </div>
                    
                    <a href="{link}" target="_blank" class="ln-link block mb-2 shrink-0 overflow-hidden mt-1 z-0 cursor-pointer group">
                        <h2 class="text-lg md:text-xl font-bold text-gray-100 leading-tight group-hover:text-[#00E5FF] transition duration-200 line-clamp-3 break-words">{titulo}</h2>
                    </a>
                    
                    <div class="text-gray-300 text-sm flex-grow overflow-y-auto no-scrollbar pr-1 mt-2 space-y-2 break-words select-text">
                        {vinetas}
                    </div>
                    
                    <div class="shrink-0 mt-3 pt-3 border-t border-white/10 flex flex-wrap items-center justify-between gap-2 select-none">
                        <div class="flex flex-wrap gap-1.5">
                            {tags_html}
                        </div>
                        {badge_clon}
                    </div>
                </article>
                """
    
# --- PURGA DE HISTORIAL VIEJO ---
historial_viejo_limpio = ""
if os.path.exists("historial.txt"):
    with open("historial.txt", "r", encoding="utf-8") as f:
        contenido_previo = f.read()

    sopa_vieja = BeautifulSoup(contenido_previo, 'html.parser')
    for tarjeta in sopa_vieja.find_all('article'):
        tag_tiempo = tarjeta.find('span', class_='tiempo-noticia')
        if tag_tiempo and tag_tiempo.has_attr('data-timestamp'):
            try:
                dt_tarjeta = datetime.fromisoformat(tag_tiempo['data-timestamp'].replace('Z', '+00:00'))
                if (datetime.now(timezone.utc) - dt_tarjeta).total_seconds() / 3600 > 48:
                    tarjeta.decompose()
                    continue
            except Exception:
                pass
        
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
        except Exception:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)

articulos_ordenados = sorted(todos_los_articulos, key=obtener_fecha_segura, reverse=True)

urls_historial = set()
articulos_unicos = []

for articulo in articulos_ordenados:
    enlace = articulo.find('a', class_='ln-link')
    if enlace and 'href' in enlace.attrs:
        link_articulo = enlace['href']
        if link_articulo not in urls_historial:
            urls_historial.add(link_articulo)
            articulos_unicos.append(articulo)
    else:
        articulos_unicos.append(articulo)

max_noticias = 100
articulos_finales = articulos_unicos[:max_noticias]
historial_recortado = "\n".join([str(art) for art in articulos_finales])

with open("historial.txt", "w", encoding="utf-8") as f:
    f.write(historial_recortado)

# --- 4. EXTRACCIÓN DEL MERCADO BURSÁTIL Y DEPORTES ---
print("Obteniendo cotizaciones del mercado...")
widgets_html = ""

# Extracción de Dólares y Variación Diaria Real (ArgentinaDatos unificado)
dict_dolares = {}
try:
    req_arg = requests.get("https://api.argentinadatos.com/v1/finanzas/dolares", timeout=10)
    if req_arg_dolar := (req_arg.status_code == 200):
        data_dolares = req_arg_dolar.json()
        from collections import defaultdict
        casa_data = defaultdict(list)
        for entry in data_dolares:
            casa_data[entry["casa"]].append(entry)
            
        casas_mapeo = {"oficial": "OFICIAL", "blue": "BLUE", "mep": "MEP", "ccl": "CCL"}
        for casa, nombre in casas_clave.items():
            if casa in casa_data and len(casa_data[casa]) > 1:
                historial = sorted(casa_panel := casa_data if (casa_data := casas_clave) else casas_clave) # Se usa el orden cronológico nativo de la API
                historial = sorted(data_dolar := [d for d in data_dolar_json if d["casa"] == casa] if 'data_url' else [d_info], key=lambda x: x.get('fecha', ''))
                
                # Intentamos usar la API de ArgentinaDatos directamente
                req_dolar_api = requests.get("https://dolarapi.com/v1/dolares", timeout=5)
                if req_dolar_api.status_code == 200:
                    dolares_res = req_dolar_get = req_dolar.json()
                    d_info = next((d for d in dolares {casa: nombre} for d in dolares if d["casa"] == casa), None)
except Exception:
    pass

# Reset manual limpio para dólares y riesgo país desde DolarAPI + ArgentinaDatos histórico
widgets_html = ""
oficial_venta = 1.0

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
                
                color_var = "text-[#00E5FF]"
                if casa != "oficial":
                    brecha = ((venta / oficial_venta) - 1) * 100
                    brecha_txt = f"Brecha {brecha:.1f}%"
                else:
                    brecha_txt = "---"

                widgets_html += f"""
                <div class="bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-6 flex flex-col justify-center min-w-[210px] flex-1 shadow-[0_8px_30px_rgb(0,0,0,0.5)]">
                    <div class="flex items-center justify-between mb-1">
                        <div class="flex items-center gap-2">
                            <span class="text-xs text-gray-400 font-bold tracking-widest uppercase">DÓLAR {nombre}</span>
                            <span class="text-gray-500 text-xs">🇦🇷</span>
                        </div>
                    </div>
                    <div class="flex items-baseline justify-between w-full mt-2">
                        <span class="text-3xl md:text-4xl font-mono font-black text-white">${int(venta) if venta % 1 == 0 else venta}</span>
                        <span class="{color_var} text-sm md:text-base font-mono font-black">0.00%</span>
                    </div>
                    <div class="mt-3 border-t border-[#232323] pt-2 flex justify-between text-[11px] text-gray-500 font-mono uppercase font-semibold">
                        <span>C: ${int(compra)}</span>
                        <span>{brecha_txt}</span>
                    </div>
                </div>
                """
except Exception:
    pass

try:
    req_rp = requests.get("https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais", timeout=10)
    if req_rp.status_code == 200:
        datos_rp = req_rp.json()
        if datos_rp and len(datos_rp) > 1:
            ultimo_rp = datos_rp[-1]["valor"] 
            rp_ayer = datos_rp[-2]["valor"]
            dif_puntos = ultimo_rp - rp_ayer
            pct_var = (dif_puntos / rp_ayer) * 100 if rp_ayer else 0
            
            if dif_puntos < 0:
                color_var = "text-[#00E5FF]"
                simbolo = "▼"
                signo = ""
            elif dif_puntos > 0:
                color_var = "text-rose-500"
                simbolo = "▲"
                signo = "+"
            else:
                color_var = "text-gray-500"
                simbolo = ""
                signo = ""
                
            widgets_html += f"""
            <div class="bg-[#1A1A1A] border border-[#2A2A2A] rounded p-5 flex flex-col justify-center min-w-[210px] flex-1 shadow-lg">
                <div class="flex items-center gap-2 mb-1">
                    <span class="text-xs text-rose-400 font-bold tracking-widest uppercase">RIESGO PAÍS</span>
                    <span class="text-gray-500 text-xs">🇦🇷</span>
                </div>
                <div class="flex items-baseline justify-between w-full mt-1">
                    <span class="text-3xl md:text-4xl font-mono font-bold text-white">{int(ultimo_rp)}</span>
                    <span class="{color_var} text-sm md:text-base font-mono font-bold">{simbolo}{abs(dif_puntos)} ({signo}{pct_var:.2f}%)</span>
                </div>
                <div class="mt-3 border-t border-[#232323] pt-2 flex justify-between text-[11px] text-gray-500 font-mono uppercase font-semibold">
                    <span>CIERRE ANTERIOR</span>
                    <span>Ayer: {int(rp_ayer)}</span>
                </div>
            </div>
            """
except Exception:
    pass

# 4.3 Partidos de Deportes en Vivo (Scraping a Promiedos)
partidos_html = ""
try:
    headers_promiedos = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    req_promiedos = requests.get("https://www.promiedos.com.ar/", headers=headers_promiedos, timeout=8)
    if req_promiedos.status_code == 200:
        soup_promiedos = BeautifulSoup(req_promiedos.text, 'html.parser')
        partidos_extraidos = []
        
        filas_partidos = soup_promiedos.find_all('tr')
        for p in filas_partidos:
            t1 = p.find('span', class_='game-t1')
            t2 = p.find('span', class_='game-t2')
            if not t1 or not t2: continue
            
            estado = p.find('td', class_='game-time')
            if not estado: continue
            
            txt_estado = estado.text.strip()
            txt_t1 = t1.text.strip()
            txt_t2 = t2.text.strip()
            
            r1 = p.find('td', class_='game-r1')
            r2 = p.find('td', class_='game-r2')
            str_res = f"{r1.text.strip()} - {r2.text.strip()}" if r1 and r2 else "vs"
            
            color_res = "text-[#00E5FF]" if "'" in txt_estado or "PT" in txt_estado or "ST" in txt_estado or "Pen" in txt_estado else "text-white"
            
            partidos_extraidos.append(f"""
                <div class='flex flex-col text-center border-l border-[#2A2A2A] pl-5 min-w-max'>
                    <span class='text-[9px] text-gray-500 font-mono tracking-wider uppercase'>{txt_estado}</span>
                    <div class='text-sm font-bold text-gray-200 mt-1 flex gap-3 items-center'>
                        <span>{txt_t1}</span> 
                        <span class='{color_res} text-lg px-2 bg-[#111] rounded border border-[#222] shadow-inner font-mono font-bold'>{str_res}</span> 
                        <span>{txt_t2}</span>
                    </div>
                </div>
            """)
            if len(partidos_extraidos) >= 8: break 
        
        if partidos_extraidos:
            partidos_html = f"""
            <div class='w-full bg-[#1A1A1A] border border-[#2A2A2A] rounded-xl p-4 mt-6 flex items-center shadow-lg overflow-x-auto no-scrollbar gap-5 max-w-7xl mx-auto'>
                <div class='flex flex-col items-center gap-1 shrink-0 pr-2 border-r border-white/5'>
                    <span class='text-2xl animate-bounce'>⚽</span>
                    <span class='text-[9px] text-gray-400 font-bold uppercase tracking-widest font-mono'>PARTIDOS</span>
                </div>
                {''.join(partidos_extraidos)}
            </div>
            """
except Exception:
    pass

if not noticias_urgentes_ticker:
    noticias_urgentes_ticker = ["El mercado financiero opera con normalidad. Monitoreo activado."]
ticker_items = "".join([f'<span class="mx-10 flex items-center gap-2 text-base md:text-lg"><span class="text-[#00E5FF] animate-pulse">⚡</span> {tit}</span>' for tit in noticias_urgentes_ticker])

# --- 5. PLANTILLA HTML DEFINITIVA ---
html_completo = f"""<!DOCTYPE html>
<html lang="es" class="w-full h-full m-0 p-0 overflow-x-hidden">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Radar Financiero | Mercados & Actualidad</title>
    <meta name="description" content="Monitor de mercados y actualidad analizada por IA.">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&family=JetBrains+Mono:wght@400;700&display=swap');
        body {{ background-color: #050505; font-family: 'Inter', sans-serif; scroll-behavior: smooth; color: #f8fafc; overflow-x: hidden; width: 100%; padding-bottom: 80px; }}
        @media (min-width: 768px) {{ body {{ padding-bottom: 0; }} }}
        .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
        @keyframes ticker {{ 0% {{ transform: translateX(100vw); }} 100% {{ transform: translateX(-100%); }} }}
        .animate-ticker {{ display: inline-flex; white-space: nowrap; animation: ticker 35s linear infinite; }}
        .animate-ticker:hover {{ animation-play-state: paused; }}
        article b {{ color: #00E5FF; font-weight: 800; background: rgba(0, 229, 255, 0.12); padding: 0 4px; border-radius: 4px; border: 1px solid rgba(0, 229, 255, 0.2);}}
        ::-webkit-scrollbar {{ width: 6px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 4px; }}
        .no-scrollbar::-webkit-scrollbar {{ display: none; }}
        .no-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
        .line-clamp-3 {{ display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}
        .tarjeta-leida {{ opacity: 0.35 !important; filter: grayscale(80%); border-color: #1e293b !important; transition: all 0.3s ease; }}
        .glass-panel {{ background: rgba(15, 23, 42, 0.7); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.05); }}
    </style>
</head>
<body class="flex w-full min-h-screen m-0 p-0 select-none bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] relative">

    <div id="progressBar" class="fixed top-0 left-0 h-1 bg-[#00E5FF] z-[100] transition-all duration-150 shadow-[0_0_10px_#00E5FF]" style="width: 0%;"></div>

    <a href="https://www.linkedin.com/in/brian-yapura-061522156/" target="_blank" class="fixed bottom-24 md:bottom-6 right-6 bg-[#00E5FF] text-[#050505] p-3.5 rounded-full shadow-[0_0_15px_rgba(0,229,255,0.4)] hover:scale-110 transition-all z-50 flex items-center justify-center group cursor-pointer" title="Conectar en LinkedIn">
        <span class="font-black text-2xl leading-none font-mono">in</span>
    </a>

    <aside class="fixed w-64 h-screen glass-panel flex flex-col z-40 hidden md:flex shrink-0 border-r">
        <div class="p-6 border-b border-white/5 bg-[#0f172a]/50">
            <h1 class="text-2xl font-black text-white tracking-tight uppercase">RADAR <span class="text-[#00E5FF]">FINANCIERO</span></h1>
            <p class="text-[10px] text-gray-400 mt-1 font-mono tracking-widest">MONITOR DE ACTUALIDAD</p>
        </div>
        
        <div class="p-6 flex-grow overflow-y-auto flex flex-col gap-6">
            <div class="glass-panel rounded-xl p-4 text-center shadow-lg border border-white/5">
                <p id="fecha-actual" class="text-[9px] text-[#00E5FF] font-bold tracking-widest uppercase mb-1">Cargando...</p>
                <div id="reloj-digital" class="text-3xl font-mono font-black text-white tracking-wider">00:00:00</div>
                <div id="mercado-estado" class="mt-2 text-[10px] font-bold px-3 py-1 rounded-full inline-block tracking-wider">--</div>
            </div>

            <div class="space-y-3 mt-2">
                <button id="btn-ver-principales" class="nav-btn w-full glass-panel hover:bg-white/10 text-white rounded-xl py-3.5 text-xs font-bold transition tracking-wider shadow-lg flex items-center justify-between px-4 ring-1 ring-[#00E5FF]/50 text-[#00E5FF]">
                    <span class="flex items-center gap-2">🏠 Feed</span>
                </button>
                <button id="btn-ver-guardadas" class="nav-btn w-full glass-panel hover:bg-white/10 text-gray-300 rounded-xl py-3.5 text-xs font-bold transition tracking-wider shadow-lg flex items-center justify-between px-4">
                    <span class="flex items-center gap-2">🔖 Guardadas</span>
                    <span id="cont-guardadas" class="bg-gray-800 text-[10px] px-2 py-0.5 rounded-full font-mono">0</span>
                </button>
                <button id="btn-ver-leidas" class="nav-btn w-full glass-panel hover:bg-white/10 text-gray-300 rounded-xl py-3.5 text-xs font-bold transition tracking-wider shadow-lg flex items-center justify-between px-4">
                    <span class="flex items-center gap-2">👁️ Leídas</span>
                    <span id="cont-leidas" class="bg-gray-800 text-[10px] px-2 py-0.5 rounded-full font-mono">0</span>
                </button>
                <button id="btn-reset-leidas" class="w-full bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/20 rounded-xl py-3.5 text-xs font-bold transition tracking-wider shadow-lg flex items-center justify-center gap-2 mt-6">
                    🗑️ Resetear Datos
                </button>
            </div>
        </div>
    </aside>

    <nav class="md:hidden fixed bottom-0 left-0 w-full glass-panel z-50 flex justify-around items-center p-3 pb-safe border-t shadow-[0_-10px_40px_rgba(0,0,0,0.5)]">
        <button id="m-btn-feed" class="nav-btn-mobile flex flex-col items-center gap-1 text-[#00E5FF]">
            <span class="text-xl">🏠</span>
            <span class="text-[9px] font-bold tracking-wider">FEED</span>
        </button>
        <button id="m-btn-guardadas" class="nav-btn-mobile flex flex-col items-center gap-1 text-gray-500 relative">
            <span class="text-xl">🔖</span>
            <span id="m-cont-guardadas" class="absolute -top-1 -right-2 bg-rose-500 text-white text-[8px] font-bold px-1.5 rounded-full border border-black font-mono">0</span>
            <span class="text-[9px] font-bold tracking-wider">SAVED</span>
        </button>
        <button id="m-btn-leidas" class="nav-btn-mobile flex flex-col items-center gap-1 text-gray-500 relative">
            <span class="text-xl">👁️</span>
            <span id="m-cont-leidas" class="absolute -top-1 -right-2 bg-gray-700 text-white text-[8px] font-bold px-1.5 rounded-full border border-black font-mono">0</span>
            <span class="text-[9px] font-bold tracking-wider">LEÍDAS</span>
        </button>
    </nav>

    <div class="md:ml-64 w-full md:w-[calc(100vw-16rem)] flex flex-col min-h-screen">
        
        <header class="w-full bg-[#020617] border-b border-white/5 shadow-xl">
            <div class="w-full bg-[#0A0A0A] border-b border-rose-900/50 text-gray-400 text-sm py-2 overflow-hidden font-mono tracking-wide">
                <div class="animate-ticker w-full">
                    {ticker_items}
                </div>
            </div>
            <div class="w-full p-4 md:p-6 max-w-7xl mx-auto">
                <div class="flex flex-wrap gap-4 justify-between items-center w-full">
                    {widgets_html}
                </div>
                {partidos_html}
            </div>
        </header>

        <div class="sticky top-0 z-30 w-full glass-panel border-b py-3 px-4 md:px-8 shadow-xl transition-all">
            <div class="max-w-7xl mx-auto flex flex-col md:flex-row gap-4 items-center justify-between">
                <div class="relative w-full md:w-1/2">
                    <input type="text" id="buscador" placeholder="Buscar Boca, YPF, inflación..." class="w-full bg-black/40 border border-white/10 rounded-full px-5 py-2.5 text-sm text-white focus:outline-none focus:border-[#00E5FF]/50 transition shadow-inner pl-10 placeholder-gray-500 font-mono">
                    <span class="absolute left-3.5 top-2.5 text-gray-500">🔍</span>
                </div>
                <div class="flex w-full md:w-auto items-center justify-between gap-4">
                    <span id="titulo-seccion" class="text-[10px] md:text-xs font-mono text-[#00E5FF] border border-[#00E5FF]/30 bg-[#00E5FF]/10 px-4 py-1.5 rounded-full uppercase tracking-widest shadow-[0_0_10px_rgba(0,229,255,0.1)]">ÚLTIMAS NOTICIAS</span>
                    <button id="btn-sort" class="bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 px-4 py-1.5 rounded-full text-[10px] md:text-xs font-bold font-mono hover:bg-indigo-500/40 transition flex items-center gap-1.5 uppercase tracking-widest cursor-pointer">
                        ↕️ Por Impacto
                    </button>
                </div>
            </div>
        </div>

        <div class="p-4 md:p-8 w-full flex-grow max-w-7xl mx-auto box-border">
            
            <div class="w-full bg-cyan-950/20 border border-cyan-500/20 rounded-xl p-4 mb-8 text-xs text-cyan-400 font-medium flex items-center gap-3 shadow-md">
                <span class="text-xl">💡</span>
                <p><b>Info:</b> Al hacer clic en el enlace de una noticia, ésta pasará automáticamente al historial de "Leídas" para mantener tu feed limpio.</p>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 w-full animate-fadeIn" id="contenedor-noticias">
                {historial_recortado}
            </div>

            <div id="loading-spinner" class="hidden justify-center my-16 w-full">
                <div class="w-10 h-10 border-4 border-transparent border-t-[#00E5FF] rounded-full animate-spin shadow-[0_0_15px_#00E5FF]"></div>
            </div>
            
            <div class="flex justify-center mt-16 mb-20 md:mb-12 w-full">
                <button id="btn-volver-arriba" class="hidden glass-panel hover:bg-[#00E5FF] hover:text-black border border-white/10 text-gray-300 font-mono text-xs px-8 py-4 rounded-full transition-all duration-300 shadow-xl gap-2 items-center tracking-widest uppercase font-bold text-center cursor-pointer">
                    ↑ Ocultar noticias extras y volver al inicio
                </button>
            </div>
        </div>
    </div>

    <script>
        const contenedor = document.getElementById('contenedor-noticias');
        const articulosBase = Array.from(document.querySelectorAll('.tarjeta-noticia'));
        let vistaActual = "principales"; 
        let limitNoticias = 12;
        let sortByImpacto = false;

        function cargarAlmacenamiento() {{
            return {{
                leidas: JSON.parse(localStorage.getItem('noticias_leidas') || '[]'),
                guardadas: JSON.parse(localStorage.getItem('noticias_guardadas') || '[]')
            }};
        }}

        function actualizarContadores() {{
            const data = cargarAlmacenamiento();
            document.getElementById('cont-leidas').innerText = data.leidas.length;
            document.getElementById('cont-guardadas').innerText = data.guardadas.length;
            document.getElementById('m-cont-leidas').innerText = data.leidas.length;
            document.getElementById('m-cont-guardadas').innerText = data.guardadas.length;
        }}

        function aplicarFiltrosYVistas() {{
            const data = cargarAlmacenamiento();
            const textoBusqueda = document.getElementById('buscador').value.toLowerCase();
            
            let universo = articulosBase.filter(art => {{
                const url = art.getAttribute('data-url');
                const isLeida = data.leidas.includes(url);
                const isGuardada = data.guardadas.includes(url);
                
                let pasaVista = false;
                if (vistaActual === "principales") pasaVista = !isLeida && !isGuardada;
                else if (vistaActual === "leidas") pasaVista = isLeida && !isGuardada;
                else if (vistaActual === "guardadas") pasaVista = isGuardada;

                const textContent = art.textContent.toLowerCase();
                return pasaVista && textContent.includes(textoBusqueda);
            }});

            if (sortByImpacto) {{
                universo.sort((a, b) => parseInt(b.dataset.impacto || 0) - parseInt(a.dataset.impacto || 0));
            }} else {{
                universo.sort((a, b) => articulosBase.indexOf(a) - articulosBase.indexOf(b));
            }}

            contenedor.innerHTML = "";
            universo.forEach((art, index) => {{
                if (index < limitNoticias) {{
                    art.style.display = 'flex';
                    contenedor.appendChild(art);
                }}
            }});

            const btnVolver = document.getElementById('btn-volver-arriba');
            if (limitNoticias >= universo.length && universo.length > 12) {{
                btnVolver.classList.remove('hidden'); btnVolver.classList.add('flex');
            }} else {{
                btnVolver.classList.add('hidden'); btnVolver.classList.remove('flex');
            }}

            articulosBase.forEach(art => {{
                const url = art.getAttribute('data-url');
                const btnG = art.querySelector('.btn-guardar');
                if(btnG) btnG.innerText = data.guardadas.includes(url) ? "★" : "🔖";
                
                if (data.leidas.includes(url) && vistaActual === "leidas") {{
                    art.classList.add('tarjeta-leida');
                    art.querySelector('.badge-leida')?.classList.remove('hidden');
                }} else {{
                    art.classList.remove('tarjeta-leida');
                    art.querySelector('.badge-leida')?.classList.add('hidden');
                }}
            }});

            actualizarContadores();
            actualizarSeparadorAyer();
        }}

        articulosBase.forEach(art => {{
            const btnG = art.querySelector('.btn-guardar');
            if (btnG) {{
                btnG.addEventListener('click', (e) => {{
                    e.stopPropagation();
                    const url = art.getAttribute('data-url');
                    let data = cargarAlmacenamiento();

                    if (data.guardadas.includes(url)) {{
                        data.guardadas = data.guardadas.filter(u => u !== url);
                    }} else {{
                        data.guardadas.push(url);
                        data.leidas = data.leidas.filter(u => u !== url);
                    }}
                    localStorage.setItem('noticias_guardadas', JSON.stringify(data.guardadas));
                    localStorage.setItem('noticias_leidas', JSON.stringify(data.leidas));
                    
                    if(vistaActual === "guardadas" || vistaActual === "principales") {{
                        art.style.opacity = "0"; art.style.transform = "scale(0.95)";
                        setTimeout(() => {{ aplicarFiltrosYVistas(); art.style.opacity="1"; art.style.transform="scale(1)"; }}, 300);
                    }} else {{ aplicarFiltrosYVistas(); }}
                }});
            }}

            const enlaceTag = art.querySelector('a.ln-link');
            if(enlaceTag) {{
                enlaceTag.addEventListener('click', () => {{
                    if (vistaActual !== "principales") return;
                    
                    const url = art.getAttribute('data-url');
                    let leidas = JSON.parse(localStorage.getItem('noticias_leidas') || '[]');
                    if (!leidas.includes(url)) {{
                        leidas.push(url);
                        localStorage.setItem('noticias_leidas', JSON.stringify(leidas));
                    }}
                    
                    setTimeout(() => {{
                        art.style.transition = "all 0.3s ease";
                        art.style.opacity = "0";
                        art.style.transform = "scale(0.95)";
                        setTimeout(() => {{ aplicarFiltrosYVistas(); art.style.opacity="1"; art.style.transform="scale(1)"; }}, 300);
                    }}, 500); 
                }});
            }}
        }});

        document.getElementById('buscador').addEventListener('input', () => {{ limitNoticias = 12; aplicarFiltrosYVistas(); }});
        document.getElementById('btn-sort').addEventListener('click', (e) => {{
            sortByImpacto = !sortByImpacto;
            e.currentTarget.classList.toggle('bg-indigo-500/40');
            e.currentTarget.classList.toggle('ring-1');
            e.currentTarget.classList.toggle('ring-indigo-300');
            aplicarFiltrosYVistas();
        }});

        window.addEventListener('scroll', () => {{
            const winScroll = document.body.scrollTop || document.documentElement.scrollTop;
            const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
            const scrolled = height > 0 ? (winScroll / height) * 100 : 0;
            document.getElementById("progressBar").style.width = scrolled + "%";

            if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 600) {{
                const data = cargarAlmacenamiento();
                const textoBusqueda = document.getElementById('buscador').value.toLowerCase();
                const universo = articulosBase.filter(art => {{
                    const url = art.getAttribute('data-url');
                    const isLeida = data.leidas.includes(url);
                    const isGuardada = data.guardadas.includes(url);
                    let pasaVista = (vistaActual === "principales" && !isLeida && !isGuardada) || 
                                    (vistaActual === "leidas" && isLeida && !isGuardada) || 
                                    (vistaActual === "guardadas" && isGuardada);
                    return pasaVista && art.textContent.toLowerCase().includes(textoBusqueda);
                }});
                
                if (limitNoticias < universo.length) {{
                    const spinner = document.getElementById('loading-spinner');
                    spinner.classList.remove('hidden'); spinner.classList.add('flex');
                    setTimeout(() => {{
                        limitNoticias += 12;
                        aplicarFiltrosYVistas();
                        spinner.classList.add('hidden'); spinner.classList.remove('flex');
                    }}, 400);
                }}
            }}
        }});

        document.getElementById('btn-volver-arriba').addEventListener('click', () => {{
            limitNoticias = 12;
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
            setTimeout(() => aplicarFiltrosYVistas(), 400);
        }});

        function cambiarVista(vista, titulo) {{
            vistaActual = vista;
            document.getElementById('titulo-seccion').innerText = titulo;
            limitNoticias = 12;
            document.getElementById('buscador').value = ""; 
            
            document.querySelectorAll('.nav-btn').forEach(b => {{
                b.classList.remove('ring-1', 'ring-[#00E5FF]/50', 'text-[#00E5FF]');
                b.classList.add('text-gray-300');
            }});
            const btnDesk = document.getElementById(`btn-ver-${{vista}}`);
            if(btnDesk) {{ btnDesk.classList.add('ring-1', 'ring-[#00E5FF]/50', 'text-[#00E5FF]'); btnDesk.classList.remove('text-gray-300'); }}

            document.querySelectorAll('.nav-btn-mobile').forEach(b => {{
                b.classList.remove('text-[#00E5FF]');
                b.classList.add('text-gray-500');
            }});
            const btnMob = document.getElementById(`m-btn-${{vista === 'principales' ? 'feed' : vista}}`);
            if(btnMob) {{ btnMob.classList.add('text-[#00E5FF]'); btnMob.classList.remove('text-gray-500'); }}

            aplicarFiltrosYVistas();
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }}

        document.getElementById('btn-ver-principales').addEventListener('click', () => cambiarVista('principales', 'ÚLTIMAS NOTICIAS'));
        document.getElementById('btn-ver-leidas').addEventListener('click', () => cambiarVista('leidas', 'HISTORIAL DE LEÍDAS'));
        document.getElementById('btn-ver-guardadas').addEventListener('click', () => cambiarVista('guardadas', 'NOTICIAS GUARDADAS'));
        
        document.getElementById('m-btn-feed').addEventListener('click', () => cambiarVista('principales', 'ÚLTIMAS NOTICIAS'));
        document.getElementById('m-btn-leidas').addEventListener('click', () => cambiarVista('leidas', 'HISTORIAL DE LEÍDAS'));
        document.getElementById('m-btn-guardadas').addEventListener('click', () => cambiarVista('guardadas', 'NOTICIAS GUARDADAS'));

        document.getElementById('btn-reset-leidas').addEventListener('click', () => {{
            if(confirm("¿Seguro que querés resetear tu historial local y guardados?")) {{
                localStorage.removeItem('noticias_leidas');
                localStorage.removeItem('noticias_guardadas');
                cambiarVista('principales', 'ÚLTIMAS NOTICIAS');
            }}
        }});

        function actualizarReloj() {{
            const ahora = new Date();
            const opcionesHora = {{ timeZone: 'America/Argentina/Buenos_Aires', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }};
            const opcionesFecha = {{ timeZone: 'America/Argentina/Buenos_Aires', weekday: 'long', day: 'numeric', month: 'long' }};
            
            document.getElementById('reloj-digital').textContent = ahora.toLocaleTimeString('es-AR', opcionesHora);
            document.getElementById('fecha-actual').textContent = ahora.toLocaleDateString('es-AR', opcionesFecha);
            
            const dia = ahora.getDay(); 
            const hora = ahora.getHours();
            const min = ahora.getMinutes();
            const estadoEl = document.getElementById('mercado-estado');
            
            const enHorario = (hora > 10 && hora < 17) || (hora === 10 && min >= 30);
            const abierto = dia >= 1 && dia <= 5 && enHorario;

            if (abierto) {{
                estadoEl.textContent = "MERCADO ABIERTO";
                estadoEl.className = "mt-1 text-[10px] font-bold px-3 py-1 rounded-full inline-block bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 animate-pulse tracking-widest";
            }} else {{
                estadoEl.textContent = "MERCADO CERRADO";
                estadoEl.className = "mt-1 text-[10px] font-bold px-3 py-1 rounded-full inline-block bg-rose-500/10 text-rose-500 border border-rose-500/20 tracking-widest";
            }}
        }}

        function actualizarTiempos() {{
            document.querySelectorAll('.tiempo-noticia').forEach(el => {{
                const ts = el.getAttribute('data-timestamp');
                if(!ts) return; 
                const n = new Date(ts), diff = Math.floor((new Date() - n) / 60000);
                if (isNaN(diff)) return;
                
                if (diff < 60) {{
                    el.textContent = `HACE ${{diff}}m`;
                    el.className = "tiempo-noticia text-gray-300 text-[10px] font-mono bg-[#1A1A1A] border border-white/5 px-2 py-1 rounded";
                }} else if (diff < 1440) {{
                    const diffHoras = Math.floor(diff / 60);
                    el.textContent = `HACE ${{diffHoras}}h`;
                    el.className = "tiempo-noticia text-gray-400 text-[10px] font-mono bg-[#0A0A0A] border border-white/5 px-2 py-1 rounded";
                }} else {{
                    el.textContent = 'AYER';
                    el.className = "tiempo-noticia text-gray-600 text-[10px] font-mono bg-transparent border border-white/5 px-2 py-1 rounded";
                }}
            }});
        }}
        
        function actualizarSeparadorAyer() {{
            const sep = document.getElementById('separador-ayer-dinamico');
            if(sep) sep.remove();

            if (vistaActual !== "principales") return; 

            const vis = articulosBase.filter(a => a.style.display !== 'none');
            for(let i=0; i<vis.length; i++) {{
                const t = vis[i].querySelector('.tiempo-noticia').textContent;
                if(t.includes('AYER')) {{
                    const div = document.createElement('div');
                    div.id = 'separador-ayer-dinamico';
                    div.className = 'col-span-1 md:col-span-2 xl:col-span-3 flex items-center gap-4 my-10 w-full';
                    div.innerHTML = '<div class="h-px bg-rose-900/40 flex-grow"></div><span class="text-[10px] font-mono text-rose-500 border border-rose-500/30 bg-rose-950/20 px-6 py-2 rounded-full uppercase tracking-widest shadow-[0_0_15px_rgba(244,63,94,0.15)]">NOTICIAS DEL DÍA ANTERIOR</span><div class="h-px bg-rose-900/40 flex-grow"></div>';
                    vis[i].parentNode.insertBefore(div, vis[i]);
                    break;
                }}
            }}
        }}
        
        aplicarFiltrosYVistas();
        actualizarTiempos();
        actualizarReloj();
        setInterval(actualizarTiempos, 60000);
        setInterval(actualizarReloj, 1000);
    </script>
</body>
</html>"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html_completo)

print("✅ Archivo index.html generado con éxito.")
