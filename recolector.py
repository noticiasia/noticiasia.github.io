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

# --- 2. EL RECOLECTOR MULTI-FUENTE (Tus 7 fuentes) ---
fuentes = [
    {"nombre": "ÁMBITO", "url": "https://www.ambito.com/", "base": "https://www.ambito.com"},
    {"nombre": "INFOBAE", "url": "https://www.infobae.com/", "base": "https://www.infobae.com"},
    {"nombre": "TN", "url": "https://tn.com.ar/", "base": "https://tn.com.ar"},
    {"nombre": "OLÉ", "url": "https://www.ole.com.ar/", "base": "https://www.ole.com.ar"},
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
            
            # --- NUEVA TÁCTICA CAJA FUERTE PARA OLÉ ---
            if fuente["nombre"] == "OLÉ":
                # Buscamos directamente las cajas de artículos
                cajas_articulo = sopa.find_all('article')
                
                for caja in cajas_articulo:
                    # Adentro de la caja, buscamos el título real
                    titulo_tag = caja.find(['h1', 'h2', 'h3', 'h4', 'h5'])
                    if not titulo_tag:
                        continue
                        
                    texto_limpio = " ".join(titulo_tag.text.split())
                    if len(texto_limpio) < 20:
                        continue
                        
                    # Buscamos el link que pertenece a esa caja
                    enlace_tag = caja.find('a')
                    if not enlace_tag:
                        continue
                        
                    link = enlace_tag.get('href', '')
                    
                    # Filtro anti-basura y anti-autores
                    if not link or any(prohibido in link.lower() for prohibido in palabras_prohibidas):
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
                            
            # --- TÁCTICA PARA EL RESTO DE LOS DIARIOS ---
            else:
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

# --- 3. EL CEREBRO DE LA IA (Sin Sociedad ni Tecnología) ---
prompt = f"""
Eres un editor experto de noticias. Aquí tienes {len(noticias_finales)} noticias de hoy:
{texto_para_ia}

REGLAS ESTRICTAS:
1. Clasifica obligatoriamente cada noticia en una de estas 4 categorías: DEPORTES, POLÍTICA, ECONOMÍA o MERCADOS. (MERCADOS es solo para bolsa, dólar, trading). ESTÁ PROHIBIDO USAR LA CATEGORÍA "SOCIEDAD" O "TECNOLOGÍA".
2. Si la noticia es de "OLÉ" y su contenido NO es deportivo, DESCÁRTALA.
3. Escribe un RESUMEN EXTENDIDO de entre 40 y 60 palabras, brindando detalles profundos.

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
                    borde, pill = "border-emerald-500", "bg-emerald-
