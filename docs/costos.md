# Declaración de costos

## Alcance

Esta estimación corresponde a una operación básica del proyecto en `us-east-1`, con el frontend en AWS Amplify y el backend en una instancia EC2.

Los valores son aproximados y deben contrastarse con AWS Cost Explorer después del evento.

## Arquitectura utilizada

```text
Frontend: AWS Amplify
Backend:  EC2 Ubuntu
Proxy:    Nginx
Datos:    Estado temporal en memoria
Mapa:     OpenStreetMap
```

No se incluye S3, Redis, DynamoDB, ElastiCache ni un balanceador de carga porque no forman parte de la arquitectura actualmente desplegada.

## Estimación mensual

| Servicio | Supuesto | Estimación |
|---|---|---:|
| EC2 | Instancia pequeña encendida todo el mes | USD 15–20 |
| EBS | Volumen gp3 de 20 GiB | USD 2–3 |
| Amplify | Hosting y tráfico bajo de demo | USD 0–5 |
| CloudWatch | Logs y métricas básicas | USD 0–3 |
| Route/DNS | Dominio gratuito o DNS externo | USD 0 |
| **Total estimado** |  | **USD 17–31/mes** |

El costo real depende del tipo exacto de instancia, horas encendida, transferencia, logs y uso durante la prueba.

## Costo durante el evento

Completar después de la demostración con datos de:

```text
AWS Billing → Bills / Cost Explorer
```

```text
Costo real del evento: USD ______
Periodo medido: __________________
Cuenta/región: us-east-1
```

## Control de costos

- AWS Budget configurado en la cuenta.
- Alertas recomendadas al 80% y 100% del presupuesto.
- No se utilizan claves AWS dentro del repositorio.
- El puerto SSH debe restringirse a la IP del equipo después de la configuración.
- La instancia EC2 debe detenerse cuando termine la demostración si no se necesita mantener la URL activa.

## Limitaciones

Esta declaración no representa una cotización oficial. Los precios finales deben verificarse en la cuenta AWS y en la región `us-east-1`.
