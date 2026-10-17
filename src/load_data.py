"""Fase 1 - Carga de datos.
 
Recorre las carpetas de correos en data/raw, abre cada correo con el modulo
`email` y extrae los campos: subject, from, body, is_html, has_attachment y label.
"""
 
import email
from pathlib import Path
 
from bs4 import BeautifulSoup
 
# Ruta absoluta a data/raw, calculada desde la ubicacion de este archivo
# (asi funciona sin importar desde que carpeta se ejecute el script).
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
 
 
def strip_html(html):
    """Quita las etiquetas HTML y devuelve solo el texto.
 
    Usa BeautifulSoup porque el HTML de spam suele estar mal formado; ademas
    convierte entidades como &nbsp;, &amp; o &cent; en sus caracteres reales.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text(separator=" ")
    # Colapsa espacios, tabs y saltos de linea repetidos en un solo espacio.
    return " ".join(texto.split())
 
 
def decode_part(part):
    """Convierte una parte del correo (que puede venir codificada) en texto."""
    data = part.get_payload(decode=True)
    if data is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return data.decode(charset, errors="replace")
    except LookupError:
        # Charset desconocido: se fuerza utf-8 para no romper la lectura.
        return data.decode("utf-8", errors="replace")
 
 
def parse_email(path):
    """Lee un correo y devuelve sus campos en un diccionario."""
    with open(path, "rb") as f:
        msg = email.message_from_binary_file(f)
 
    plain_parts = []
    html_parts = []
    has_attachment = False
 
    for part in msg.walk():
        if part.is_multipart():
            continue  # Los contenedores no tienen texto, se saltan.
        if part.get_filename():
            has_attachment = True  # Si la parte tiene nombre de archivo, es adjunto.
            continue
        content_type = part.get_content_type()
        if content_type == "text/plain":
            plain_parts.append(decode_part(part))
        elif content_type == "text/html":
            html_parts.append(decode_part(part))
 
    is_html = len(html_parts) > 0  # Marca si el correo traia parte HTML.
    if plain_parts:
        body = "\n".join(plain_parts)  # Preferimos el texto plano si existe.
    else:
        # Solo aqui el cuerpo viene de HTML, asi que se limpia con strip_html.
        body = strip_html("\n".join(html_parts))
 
    return {
        "subject": msg["Subject"],
        "from": msg["From"],
        "body": body,
        "is_html": is_html,
        "has_attachment": has_attachment,
    }
 
 
def label_from_folder(folder_name):
    """Asigna la etiqueta segun el nombre de la carpeta: spam -> 1, ham -> 0."""
    return 1 if folder_name.startswith("spam") else 0
 
 
def load_dataset(raw_dir=RAW_DIR):
    """Recorre las carpetas y devuelve una lista de correos con su label.
 
    Devuelve una tupla (emails, errores): la lista de correos y una lista con el
    motivo de cada correo que no se pudo leer.
    """
    emails = []
    errores = []  # Anota cada correo fallido para poder reportarlo al final.
    for folder in sorted(raw_dir.iterdir()):
        if not folder.is_dir():
            continue
        label = label_from_folder(folder.name)
        for file_path in folder.iterdir():
            if not file_path.is_file():
                continue
            if file_path.name == "cmds":
                continue  # El archivo 'cmds' no es un correo, se salta.
            try:
                record = parse_email(file_path)
            except Exception as exc:
                # Se omite el correo corrupto, pero se registra el motivo.
                errores.append((str(file_path), repr(exc)))
                continue
            record["label"] = label
            emails.append(record)
    return emails, errores
 
 
if __name__ == "__main__":
    datos, errores = load_dataset()
    print("Correos cargados:", len(datos))
    print("Correos omitidos:", len(errores))
    for ruta, motivo in errores:
        print("  -", ruta, "->", motivo)
    spams = sum(1 for d in datos if d["label"] == 1)
    print("Spam:", spams, "| Ham:", len(datos) - spams)
    if datos:
        for clave, valor in datos[0].items():
            print(clave, ":", str(valor)[:200])   