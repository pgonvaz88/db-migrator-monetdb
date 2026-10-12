---
trigger: always_on
---

# Reglas de Entorno y Configuración del IDE

## Entorno y Ejecución

- Consulta y respeta siempre las opciones definidas en `.vscode/settings.json`.
- Utiliza exclusivamente el intérprete de Python configurado en el workspace (`.venv/bin/python` o `.\.venv\Scripts\python.exe`).
- Todo comando de terminal, test o script debe ejecutarse dentro del entorno virtual `.venv`.

## Estilo y Calidad de Código

- Aplica las reglas de formato y linters configuradas en el proyecto (Ruff / Black / Prettier).
- No modifiques configuraciones existentes en `.vscode/` a menos que se solicite explícitamente.

## Reglas de Código

- Usa siempre la sintaxis de ES6+ (Arrow functions, async/await).
- No uses librerías externas para las migraciones si se puede hacer con SQL nativo.
- Añade comentarios breves en las funciones complejas explicando el porqué, no el qué.
