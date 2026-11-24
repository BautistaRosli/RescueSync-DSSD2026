# Sesión con Cloud y permisos locales

El frontend conserva sus contratos: envía credenciales al backend y recibe el JWT
de Cloud sin modificaciones, junto con el perfil y rol de RescueSync. Cloud
autentica; el backend aplica sus permisos consultando su propia base.

## Configuración

1. Ejecutar Cloud en el puerto **8002** y el backend en **8000**.
2. Configurar `JWT_SECRET` con el mismo secreto privado en ambas APIs.
3. Configurar las variables del backend antes de iniciar el proceso:

| Variable | Valor |
| --- | --- |
| `CLOUD_API_URL` | `http://127.0.0.1:8002` local; `http://host.docker.internal:8002` desde Docker |
| `JWT_ISSUER` | `rescuesync-cloud` |
| `JWT_AUDIENCE` | `rescuesync-backend` |

Cloud debe emitir la audiencia `rescuesync-backend` además de su propia audiencia
`rescuesync-cloud`. El backend fija HS256 y exige `sub`, `usuario`, `iat`, `exp`,
`iss` y `aud`. `usuario` debe coincidir exactamente con el email del login; en las
peticiones siguientes identifica el perfil local. El ID remoto de `sub` puede
ser distinto del ID local. Los roles del token no conceden permisos locales.

## Login y registro

- `POST /api/v1/auth/login`: conserva entrada `email`, `password` y salida
  `access_token`, `token_type`, `rol`, `usuario`. Nunca autentica contra hashes
  locales. Una cuenta Cloud sin perfil local recibe 401; un perfil inactivo, 403.
- `POST /api/v1/auth/registro`: conserva los datos personales, rol y organización.
  Primero valida duplicado, rol y organización locales; después crea credenciales
  en Cloud y obtiene un JWT válido antes de guardar el perfil. Devuelve 201 con
  el mismo contrato de sesión. Los perfiles nuevos usan el marcador no
  autenticable `!cloud` en `password_hash`, sin copiar la contraseña.
- `GET /api/v1/auth/me` y las rutas protegidas validan el JWT de Cloud y resuelven
  el email firmado, el estado activo y los permisos en la base local.

Cloud no disponible, una respuesta malformada o un token remoto inválido devuelve
503 sin exponer respuestas internas. Cloud rechazando credenciales devuelve 401.
El transporte tiene un límite de espera de 10 segundos por petición.

## Cuentas existentes y reintentos

Los hashes anteriores se conservan, pero ya no permiten iniciar sesión. Los
usuarios existentes y los perfiles iniciales necesitan credenciales creadas por
separado en Cloud con el mismo email. La siembra no crea cuentas remotas ni
contraseñas locales. Los JWT anteriores del backend dejan de ser válidos: hay
que volver a iniciar sesión.

El registro abarca dos bases y no es una transacción distribuida. Si Cloud creó
la cuenta y luego falló la persistencia local, puede quedar solo la cuenta
remota. Reintentar el registro con las mismas credenciales permite completarlo:
un 409 de Cloud exige un login correcto antes de guardar el perfil. Una contraseña
distinta no permite adoptar la cuenta. Los errores de persistencia revierten el
trabajo local pendiente; no se borra automáticamente la cuenta remota.
