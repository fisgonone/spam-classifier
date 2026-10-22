"""Fase 1 - Carga y limpieza de datos.

Recorre las carpetas de correos en data/raw, abre cada correo con el modulo
`email` y extrae los campos: subject, from, body, is_html, has_attachment y label.
Despues limpia el dataset (vacios y duplicados) y lo guarda en
data/processed/emails.csv.
"""

import email
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

# Ruta absoluta a la raiz del repo, calculada desde la ubicacion de este archivo
# (asi funciona sin importar desde que carpeta se ejecute el script).
ROOT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT_DIR / "data" / "raw"
PROCESSED_DIR = ROOT_DIR / "data" / "processed"


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


def clean_dataset(df):
    """Quita correos sin cuerpo y correos duplicados.

    Primero los vacios: si no, todos los cuerpos vacios cuentan como
    "duplicados" entre si y el conteo de duplicados queda inflado.
    Dos correos son duplicados si tienen el mismo cuerpo: para el modelo
    son el mismo ejemplo, aunque los encabezados (fecha, servidores) cambien.
    """
    sin_cuerpo = df["body"].str.strip() == ""
    df = df[~sin_cuerpo]
    df = df.drop_duplicates(subset=["body"], keep="first")
    return df.reset_index(drop=True)


if __name__ == "__main__":
    datos, errores = load_dataset()
    print("Correos cargados:", len(datos))
    print("Correos omitidos:", len(errores))
    for ruta, motivo in errores:
        print("  -", ruta, "->", motivo)

    df = pd.DataFrame(datos)
    total = len(df)
    vacios = (df["body"].str.strip() == "").sum()

    df_limpio = clean_dataset(df)
    duplicados = total - vacios - len(df_limpio)

    print("Sin cuerpo eliminados:", vacios)
    print("Duplicados eliminados:", duplicados)
    print("Filas finales:", len(df_limpio))
    print(df_limpio["label"].value_counts())

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    salida = PROCESSED_DIR / "emails.csv"
    df_limpio.to_csv(salida, index=False, encoding="utf-8")
    print("Guardado en:", salida)