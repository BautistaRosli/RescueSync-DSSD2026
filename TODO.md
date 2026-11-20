- falta implementar la vista del municipio para que seleccione una oferta despues de que se hayan validado
- Falta implementar la conexion con la api para la solicitud de bloqueo de recursos cuando se selecciona una oferta validada
---
---
> resumen de como conectar con la api para bloquear recursos 
# Integración API — Bloqueo de recursos
1. Autenticación
Todas las llamadas requieren un JWT. Primero se obtiene el token:
POST /auth/login
Content-Type: application/json
{
  "usuario": "usuario-rescuesync",
  "password": "password"
}
Respuesta:
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600
}
Luego, en cada request:
Authorization: Bearer <access_token>
2. Bloquear recursos
POST /recursos/bloquear
Authorization: Bearer <access_token>
Content-Type: application/json
Request
{
  "emergencia_id": 12,
  "lote_id": 3,
  "ongs": [
    {
      "ong_id": 1,
      "items": [
        { "item_id": 101, "cantidad": 20 }
      ]
    },
    {
      "ong_id": 3,
      "items": [
        { "item_id": 101, "cantidad": 2 },
        { "item_id": 105, "cantidad": 1 }
      ]
    }
  ]
}
Campos:
Campo	Obligatorio	Descripción
emergencia_id	Sí	Emergencia a la que se asocian los bloqueos
lote_id	No	Lote asociado; si se omite queda null
ongs	Sí	Una o más ONGs, no puede estar vacío
ong_id	Sí	Id de la ONG
items	Sí	Uno o más items de esa ONG, no puede estar vacío
item_id	Sí	Id del tipo de recurso del catálogo items
cantidad	Sí	Entero mayor a 0
También se acepta tipo_recurso_id o recurso_id en lugar de item_id, y una lista plana con asignaciones, items, recursos o bloqueos en la raíz. El formato recomendado es el agrupado por ONG mostrado arriba.
3. Respuesta exitosa
200 OK
{
  "emergencia_id": 12,
  "lote_id": 3,
  "total_bloqueado": 23,
  "bloqueados": [
    { "ong_id": 1, "item_id": 101, "cantidad": 20, "estado": "BLOQUEADO" },
    { "ong_id": 3, "item_id": 101, "cantidad": 2,  "estado": "BLOQUEADO" },
    { "ong_id": 3, "item_id": 105, "cantidad": 1,  "estado": "BLOQUEADO" }
  ]
}
Cada item bloqueado queda registrado en compromisos_recurso con estado BLOQUEADO. El inventario de la ONG no se modifica; la disponibilidad pasa a calcularse como:
disponible = cantidad_ong_items - compromisos BLOQUEADO/COMPROMETIDO
4. Reglas importantes
- La operación es atómica: si una ONG, item o cantidad falla, no se bloquea nada.
- Se valida que:
- la ONG exista y esté activa,
- el item exista,
- la ONG tenga ese item asignado en su inventario,
- haya stock suficiente sin comprometer.
- Si se envían items repetidos para la misma ONG, se suman y se bloquean una sola vez.
- El endpoint usa locks de fila en PostgreSQL (SELECT ... FOR UPDATE) sobre ongs, items y ong_items, por lo que soporta llamadas concurrentes sin sobrebloquear stock.
- No es idempotente: cada llamada exitosa crea nuevos compromisos. Si la otra aplicación puede reintentar la misma operación, debe hacerlo solo cuando el request anterior haya fallado antes de recibir respuesta; si se necesita seguridad ante reintentos, conviene agregar una clave de idempotencia o validar por emergencia_id + lote_id.
5. Errores
Código	Motivo
401	Token ausente, inválido o expirado
404	La ONG o el item no existe
409	ONG inactiva, item no asignado a la ONG o stock insuficiente
422	Body inválido: falta un campo, cantidad <= 0, lista vacía, etc.
503	La API no está configurada o la base no está disponible
Ejemplo de error por stock:
{
  "detail": "La ONG 3 no tiene stock suficiente del item 101: solicitado 30, disponible 25"
}
Ejemplo de error por item no asignado:
{
  "detail": "La ONG 3 no tiene asignado el item 105"
}
6. Ejemplo completo
## 1. Login
curl -X POST http://localhost:8002/auth/login \
  -H "Content-Type: application/json" \
  -d '{"usuario":"usuario-rescuesync","password":"password"}'

## 2. Bloquear
curl -X POST http://localhost:8002/recursos/bloquear \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "emergencia_id": 12,
    "lote_id": 3,
    "ongs": [
      {
        "ong_id": 1,
        "items": [
          { "item_id": 101, "cantidad": 20 }
        ]
      }
    ]
  }'
La otra aplicación solo necesita: hacer login, guardar el access_token, enviar el bloqueo con el header Authorization y tratar 200 como operación confirmada; cualquier 4xx/5xx significa que no se bloqueó nada.
> termino el resumen
---
---

sigue