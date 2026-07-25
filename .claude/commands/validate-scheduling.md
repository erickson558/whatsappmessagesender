# Skill: /validate-scheduling — Auditoría de la Capa de Programación de Mensajes

## Cuándo usar esta skill

- El usuario reporta que los mensajes de **uno o varios grupos de trabajo** (Grupo 1-4) no se envían, mientras otros sí.
- Un mensaje con repetición (Semanalmente/Mensualmente) + días de la semana restringidos parece enviarse a una hora incorrecta o dejar de enviarse.
- Se agregó o modificó lógica en `_schedule_messages_group`, `schedule_all_messages`, `_process_scheduled_message`, `_reprogram_repeat`, `_advance_to_next_occurrence` o `_reschedule_past_due_repeating_messages` en `frontend/gui.py`.
- Antes de compilar un release, como complemento de `/diagnose-bot` (que audita browser/conexión, NO la capa de programación).

## Contexto: por qué existe esta skill

En V8.9.14 se confirmaron dos bugs reales en esta capa que **nunca habrían aparecido en `/diagnose-bot`** porque ese skill solo revisa `browser_worker.py` (conexión, keepalive, selección de contacto). Ambos bugs vivían en `frontend/gui.py`, en la lógica que decide QUÉ mensaje se programa y CUÁNDO:

1. `_schedule_messages_group` hacía `return []` ante la primera fila con hora/fecha inválida, descartando **todos** los mensajes ya válidos de esa misma pestaña — un grupo de trabajo entero podía dejar de enviar nada por una sola fila mal configurada.
2. En el contenedor compartido de items de grupo (`_process_scheduled_message`), el filtro de "días permitidos" se evaluaba sin comprobar si el item ya estaba vencido, y al reprogramar sobreescribía `item["datetime"]` con `datetime.now()` — perdiendo la hora configurada de un mensaje hermano que aún no le tocaba enviarse.

Ninguno de los dos generaba un error visible ni un log de fallo: el síntoma era simplemente "el mensaje nunca llegó". Por eso esta skill existe como checklist dedicado a esa clase de bug silencioso.

---

## Lo que hace esta skill

1. **Independencia por mensaje dentro de un grupo** — `_schedule_messages_group` (frontend/gui.py):
   - ¿Una fila inválida (hora/minuto/AM-PM vacío, fecha no parseable) usa `continue` para saltar SOLO esa fila? (❌ si usa `return []` o cualquier forma de abortar el resto de la pestaña)
   - ¿Una fila con "Enviar" desactivado se salta sin afectar a las demás?

2. **Filtro de días vs. vencimiento** — `_process_scheduled_message`, rama `is_group` (frontend/gui.py):
   - ¿El filtro `days` se evalúa SOLO sobre items ya vencidos (`item_dt <= now + tolerancia`)? (❌ si se evalúa incondicionalmente en cada disparo del contenedor compartido)
   - ¿Al reprogramar por día no permitido se preserva `item["datetime"].time()` original? (❌ si usa `datetime.now() + timedelta(days=delta)` sin anclar la hora original)
   - ¿La misma protección aplica al branch equivalente de mensajes individuales (no agrupados), más abajo en el mismo método?

3. **Agrupación por (datetime, contact)** — `schedule_all_messages`:
   - Confirmar que dos filas de distintos grupos con el mismo contacto y el mismo instante exacto quedan unidas en un solo contenedor `is_group`, y que eso es intencional (permite un solo `select_contact` para varios mensajes), no un bug de indexación.

4. **Validación de contacto multi-palabra / apodos** — `backend/browser_worker.py`:
   - ¿`_select_contact` tiene una vía de autoconsistencia para cuando el nombre en pantalla es más corto que el configurado (comparar contra el candidato que la propia app clickeó, NO contra el `contact` completo ni un umbral genérico de similitud)? Aflojar `_like_match`/`_is_in_chat` de forma genérica reabre el bug de cruce de contactos de V8.9.13 — si se detecta, marcarlo como regresión crítica.

5. **Tests de regresión** — confirmar que existen y pasan:
   - `tests/test_gui_schedule_messages_group.py`
   - `tests/test_gui_group_day_filter.py`
   - `tests/test_browser_worker_partial_name_match.py`
   - `tests/test_browser_worker_contact_targeting.py`

---

## Instrucciones para el agente

1. Ejecutar `python -m pytest tests/ -v` y reportar resultado completo.
2. Leer `frontend/gui.py`: `_schedule_messages_group`, `schedule_all_messages`, `_process_scheduled_message` (ambas ramas: `is_group` y standalone), `_reprogram_repeat`, `_retry_message_delivery`, `_advance_to_next_occurrence`, `_reschedule_past_due_repeating_messages`.
3. Para cada checklist de arriba, marcar ✅/❌ con cita de archivo:línea.
4. Si existe `config.json` local, inspeccionar `messages_group1..4` en busca de filas con "send": true pero campos de hora/fecha vacíos o inconsistentes (indicador de que el bug #1 podría estar activo silenciosamente) y de pares de mensajes al mismo contacto con `repeat` + `days` combinados (candidatos al bug #2).
5. Si hay logs locales (`logaplicacion*.txt`, `logmensajes*.txt`), buscar contactos configurados en `config.json` que NUNCA aparezcan en ningún log — señal de que sus mensajes no se están programando/enviando, y correlacionar con los checks anteriores antes de asumir causa.

### Formato del reporte

```
## Reporte de Programación de Mensajes — WhatsApp Message Sender

**Versión:** X.Y.Z

### Checks de código
| # | Check | Estado |
|---|-------|--------|
| 1 | Fila inválida no aborta el resto del grupo (continue, no return []) | ✅ / ❌ |
| 2 | Filtro de días solo aplica a items vencidos | ✅ / ❌ |
| 3 | Reprogramación por día preserva hora original | ✅ / ❌ |
| 4 | Autoconsistencia de nombre parcial sin aflojar match genérico | ✅ / ❌ |
| 5 | Tests de regresión presentes y en verde | ✅ / ❌ |

### Config.json / logs (si disponibles)
[Filas sospechosas, contactos sin rastro en logs]

### Recomendación
[Acción sugerida — qué archivo/línea corregir si algo falla]
```

## Acción correctiva si se detectan problemas

Si algún check falla, describe el archivo y línea exactos a corregir siguiendo los mismos criterios que V8.9.14 (fix quirúrgico, sin abortar comportamiento existente — ver `.claude/specs/project-spec.md` sección "Confiabilidad" y `CHANGELOG.md` entrada v8.9.14). Tras corregir, ejecutar `/bump-version patch`, actualizar `CHANGELOG.md`, y sugerir `/build-exe` + `/github-push`.
