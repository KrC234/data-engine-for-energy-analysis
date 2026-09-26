BEGIN;

TRUNCATE TABLE
    energia.alerta,
    energia.lectura,
    energia.evento,
    energia.periodo_facturacion,
    energia.medidor,
    energia.servicio,
    energia.perfil_carga_horaria,
    energia.calendario,
    energia.corrida_generacion
RESTART IDENTITY CASCADE;

COMMIT;