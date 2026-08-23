# Guía de pruebas — emitir una factura con tu RUC

Recorrido completo con `curl`, desde levantar el servicio hasta descargar el CDR
que devuelve SUNAT. Está pensada para el **ambiente BETA**, así que puedes
seguirla con tu propio RUC sin consecuencias.

> ### Antes de empezar
>
> **Los comprobantes que envíes a BETA no tienen validez tributaria.** Es un
> validador de estructura XML y catálogos, no un registro fiscal: nada de lo que
> emitas aquí se declara ni le aparece a nadie en SUNAT.
>
> SUNAT también pide expresamente **no usar BETA para pruebas de carga**.

---

## Qué necesitas

| | |
|---|---|
| Tu RUC | 11 dígitos. Sirve tanto uno de persona natural (`10…`) como de empresa (`20…`). |
| Certificado digital | **No hace falta uno real.** BETA no lo valida; generamos uno de prueba en el paso 3. |
| Credenciales SOL | En BETA son siempre `MODDATOS` / `moddatos`, no las tuyas reales. |
| Podman o Docker | Para levantar el stack. |

Sobre tu RUC de persona natural: BETA valida la **estructura** del comprobante,
no si estás autorizado a emitir. En producción, emitir *facturas* exige estar en
un régimen que lo permita —en NRUS solo se emiten boletas— y tener el
certificado registrado en SUNAT. Para probar, tu RUC funciona igual.

---

## 1. Levantar el servicio

```bash
make env          # crea .env desde la plantilla
make secret       # copia el resultado a ENCRYPTION_KEY en .env
make admin-token  # copia el resultado a ADMIN_TOKEN en .env
make up
make migrate
```

Comprueba que responde:

```bash
curl -s http://localhost:7890/health
```

```json
{"status":"ok","service":"sunat-biller","version":"0.1.0",
 "app_env":"development","sunat_environment":"BETA"}
```

Confirma que dice `"sunat_environment":"BETA"` antes de seguir.

La documentación interactiva está en <http://localhost:7890/docs>. Con
`APP_ENV=production` no se publica.

## 2. Variables de trabajo

Ajusta el RUC y el nombre a los tuyos:

> Si tu sistema no tiene `/proc/sys/kernel/random/uuid` (macOS), usa `$(uuidgen)`
> en su lugar para la clave de idempotencia del paso 9.

```bash
export API="http://localhost:7890/api/v1"
export ADMIN_TOKEN="…el que pusiste en .env…"
export RUC="10123456781"
export RAZON_SOCIAL="MI NEGOCIO"
```

## 3. Generar el certificado de prueba

```bash
make test-cert RUC=$RUC NAME="$RAZON_SOCIAL"
```

Imprime la ruta del `.pfx` y **la contraseña generada**. Guárdala:

```bash
export CERT_PATH="data/certificates/test-$RUC.pfx"
export CERT_PASS="…la que imprimió…"
```

El archivo no se versiona: el `.gitignore` excluye todos los `.pfx`.

## 4. Registrar tu empresa

Este es el único paso que usa `X-Admin-Token` en vez de una API key — todavía no
existe ninguna.

```bash
curl -s -X POST "$API/companies" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"ruc\": \"$RUC\",
    \"business_name\": \"$RAZON_SOCIAL\",
    \"address\": \"AV. SIEMPRE VIVA 742\",
    \"ubigeo\": \"150101\",
    \"department\": \"LIMA\",
    \"province\": \"LIMA\",
    \"district\": \"LIMA\",
    \"country_code\": \"PE\"
  }"
```

```json
{"id":"3f2b…","ruc":"10123456781","business_name":"MI NEGOCIO","active":true,…}
```

```bash
export COMPANY_ID="…el id que devolvió…"
```

> **Si responde 422** con `INVALID_RUC`, el dígito verificador de tu RUC no
> cuadra. El servicio lo valida con el algoritmo módulo 11 de SUNAT — revisa que
> lo hayas escrito completo y sin espacios.

## 5. Cargar las credenciales SOL

En BETA son fijas. El servicio antepone tu RUC automáticamente y forma el usuario
`{RUC}MODDATOS` que espera SUNAT, así que aquí solo va `MODDATOS`.

```bash
curl -s -X PATCH "$API/companies/$COMPANY_ID/sunat-credentials" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sol_user": "MODDATOS", "sol_password": "moddatos"}'
```

La contraseña se cifra en reposo y no vuelve a salir por la API.

## 6. Subir el certificado

Va como `multipart/form-data`:

```bash
curl -s -X POST "$API/companies/$COMPANY_ID/certificates" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -F "file=@$CERT_PATH" \
  -F "password=$CERT_PASS"
```

```json
{"id":"8a1c…","serial_number":"3141…","valid_from":"2026-08-22T…",
 "valid_until":"2028-08-22T…","active":true,…}
```

Solo puede haber un certificado activo por empresa: si subes otro, el anterior se
desactiva solo.

## 7. Crear la serie

```bash
curl -s -X POST "$API/companies/$COMPANY_ID/series" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"document_type": "01", "series": "F001", "current_number": 0}'
```

`current_number: 0` hace que la primera factura sea la `F001-00000001`.

## 8. Crear la API key

```bash
curl -s -X POST "$API/companies/$COMPANY_ID/api-keys" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "pruebas con curl"}'
```

```json
{"key":"sk_a1b2c3…"}
```

> **Guárdala ahora.** Solo se almacena su hash; no hay forma de recuperarla
> después. Si la pierdes, revoca esa y crea otra.

```bash
export API_KEY="sk_…"
```

## 9. Emitir la factura

A partir de aquí ya no se usa el token de administración, sino la API key.

Solo hacen falta los datos del negocio: **el IGV y los totales los calcula el
servicio**.

```bash
curl -s -X POST "$API/invoices" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Idempotency-Key: $(cat /proc/sys/kernel/random/uuid)" \
  -H "Content-Type: application/json" \
  -d "{
    \"issue_date\": \"$(date +%F)\",
    \"currency\": \"PEN\",
    \"series\": \"F001\",
    \"customer\": {
      \"document_type\": \"6\",
      \"document_number\": \"20000000001\",
      \"name\": \"CLIENTE DE PRUEBA SAC\"
    },
    \"items\": [
      {
        \"line_number\": 1,
        \"description\": \"SERVICIO DE CONSULTORIA\",
        \"quantity\": \"1\",
        \"unit_code\": \"ZZ\",
        \"unit_value\": \"100.00\",
        \"tax_affectation\": \"10\"
      }
    ]
  }"
```

Respuesta esperada (recortada):

```json
{
  "id": "c7d9…",
  "series": "F001",
  "number": 1,
  "filename": "10123456781-01-F001-00000001",
  "subtotal": "100.00",
  "igv_total": "18.00",
  "total": "118.00",
  "status": "ACCEPTED",
  "sunat_code": "0",
  "sunat_description": "La Factura numero F001-00000001, ha sido aceptada",
  "xml_hash": "FeG+0Q1pbb4DQIZ9ugta…"
}
```

```bash
export DOC_ID="…el id…"
```

### Cómo leer la respuesta

**Siempre revisa `status`, no solo el código HTTP.** Un rechazo de SUNAT también
llega como `200`: es una respuesta válida del servicio, no un error de tu
petición.

| `status` | Qué pasó | Qué hacer |
|---|---|---|
| `ACCEPTED` | Aceptado, `sunat_code` es `0`. | Nada. |
| `ACCEPTED_WITH_OBSERVATION` | Aceptado, pero con observaciones (`4xxx`). | Corregir para las próximas emisiones. |
| `REJECTED` | Rechazado (`2xxx`). El comprobante no existe para SUNAT. | Corregir los datos y emitir uno **nuevo**. Reenviar el mismo número no sirve. |
| `SENT` | SUNAT no respondió a tiempo. | El XML ya está firmado y guardado; se reintenta. |
| `ERROR` | Fallo técnico no recuperable. | Revisar `sunat_description`. |

## 10. Descargar el XML y el CDR

```bash
curl -s "$API/documents/$DOC_ID/xml" -H "X-API-Key: $API_KEY" -o factura.xml
curl -s "$API/documents/$DOC_ID/cdr" -H "X-API-Key: $API_KEY" -o cdr.xml
```

El XML lleva la firma dentro de `ext:UBLExtensions`. Compruébalo:

```bash
grep -o '<ds:Signature[^>]*' factura.xml
```

## 11. Consultar lo emitido

```bash
curl -s "$API/documents?page=1&page_size=20" -H "X-API-Key: $API_KEY"
curl -s "$API/documents?status=ACCEPTED&series=F001" -H "X-API-Key: $API_KEY"
```

---

## Errores frecuentes

### Del servicio

| Código | Significa |
|---|---|
| `INVALID_RUC` / `VALIDATION_ERROR` | El dígito verificador del RUC no cuadra, o falta un campo obligatorio. |
| `UNAUTHORIZED` | Falta `X-API-Key` o `X-Admin-Token`, o la clave está revocada o vencida. |
| `NOT_FOUND` con «ninguna serie activa» | Falta el paso 7, o la serie está desactivada. |
| `NOT_FOUND` con «certificado digital activo» | Falta el paso 6. |
| `CONFLICT` con «credenciales SOL» | Falta el paso 5. |
| `CONFLICT` con «varias series activas» | Tienes más de una serie para el tipo; manda `"series": "F001"` en el cuerpo. |
| `TOTALS_MISMATCH` | Enviaste importes que no coinciden con el cálculo del servicio. Lo más simple es no enviarlos. |
| `CERTIFICATE_ERROR` | Contraseña incorrecta, certificado vencido, o no es un `.pfx`/`.p12` válido. |

### De SUNAT

Los códigos vienen en `sunat_code` y se agrupan por rango:

| Rango | Qué es | ¿Reintentable? |
|---|---|---|
| `0` | Aceptado. | — |
| `100`–`999` | Falla interna de SUNAT. | Sí, con espera. |
| `1000`–`1999` | Error del emisor (RUC no habilitado, credenciales…). | No. |
| `1033` | El comprobante ya fue informado. | No: se resuelve consultando su estado. |
| `2000`–`3999` | Rechazo por el contenido del comprobante. | **Nunca.** Corregir y emitir uno nuevo. |
| `4000`+ | Observación; el comprobante se acepta igual. | — |

Los más comunes al empezar:

- **`2335`** — el XML no cumple el formato. Suele ser un catálogo mal puesto.
- **`0111`** — servicio de SUNAT no disponible. Vuelve a intentarlo.
- **`1032`** / **`1033`** — problema con el RUC o comprobante duplicado.

---

## Pasar a producción

Cuando esto funcione en BETA, para operar de verdad hace falta:

1. Un **certificado digital emitido por una entidad de certificación acreditada**
   (el de prueba no sirve) y registrado en SUNAT.
2. Estar dado de alta como **emisor electrónico** y en un régimen que permita
   emitir el tipo de comprobante.
3. Las **credenciales SOL reales** en el paso 5, en lugar de `MODDATOS`.
4. `SUNAT_ENVIRONMENT=PRODUCTION` y `APP_ENV=production` en el `.env`.
5. HTTPS delante del servicio: la aplicación no termina TLS a propósito.

Con `APP_ENV=production` dejan de publicarse `/docs`, `/redoc` y el esquema
OpenAPI, y el servicio no arranca si `ENCRYPTION_KEY`, `SECRET_KEY` o
`ADMIN_TOKEN` siguen con valores por defecto.
