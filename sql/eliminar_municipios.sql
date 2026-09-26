-- Eliminacion definitiva de la tabla `municipios` y de las columnas `municipio_id`.
--
-- Contexto: el proyecto no usa Alembic. `Base.metadata.create_all()` crea tablas
-- faltantes pero NUNCA borra tablas ni columnas, asi que quitar el codigo Python
-- no alcanza: la base de datos de desarrollo conservaba `municipios` y las dos
-- columnas `municipio_id`. Este script hace el borrado fisico.
--
-- Es DESTRUCTIVO: borra la tabla `municipios` con todos sus registros y descarta
-- los valores de `municipio_id` en `emergencias` y `usuarios`.
--
-- Ejecutar dentro de una transaccion: si algo falla, no queda aplicado a medias.

BEGIN;

-- 1. Verificar que ninguna otra tabla dependa de `municipios`.
--    Si alguien volvio a agregar una FK, el script aborta en vez de dejar
--    una referencia colgando.
DO $$
DECLARE
    referencias text;
BEGIN
    IF to_regclass('municipios') IS NULL THEN
        RETURN;
    END IF;

    SELECT string_agg(format('%I.%I', c.conrelid::regclass, a.attname), ', ')
    INTO referencias
    FROM pg_constraint c
    JOIN pg_attribute a
      ON a.attrelid = c.conrelid
     AND a.attnum = ANY (c.conkey)
    WHERE c.contype = 'f'
      AND c.confrelid = 'municipios'::regclass
      AND c.conrelid::regclass::text NOT IN ('emergencias', 'usuarios');

    IF referencias IS NOT NULL THEN
        RAISE EXCEPTION
            'Hay referencias a municipios fuera del alcance previsto: %', referencias;
    END IF;
END $$;

-- 2. Mostrar el estado previo, para tener registro de lo que se borra.
DO $$
BEGIN
    IF to_regclass('municipios') IS NOT NULL THEN
        RAISE NOTICE 'Filas en municipios: %', (SELECT count(*) FROM municipios);
    END IF;
    RAISE NOTICE 'Filas en emergencias: %', (SELECT count(*) FROM emergencias);
    RAISE NOTICE 'Filas en usuarios: %', (SELECT count(*) FROM usuarios);
END $$;

-- 3. Borrar la tabla. `CASCADE` elimina tambien las claves foraneas que la
--    referencian desde `emergencias` y `usuarios`; sin esto el DROP falla.
DROP TABLE IF EXISTS municipios CASCADE;

-- 4. Ahora que no hay FK, las columnas quedan como enteros sueltos: se descartan.
ALTER TABLE emergencias DROP COLUMN IF EXISTS municipio_id;
ALTER TABLE usuarios DROP COLUMN IF EXISTS municipio_id;

COMMIT;

-- 5. Verificar el resultado.
SELECT count(*) AS municipios_restantes
FROM information_schema.tables
WHERE table_name = 'municipios'
  AND table_schema = 'public';

SELECT table_name, column_name
FROM information_schema.columns
WHERE column_name = 'municipio_id'
  AND table_schema = 'public';
