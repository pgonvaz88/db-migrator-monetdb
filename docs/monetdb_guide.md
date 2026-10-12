# Guía Rápida de Uso: MonetDB Standalone en Windows

Esta guía contiene los pasos esenciales para iniciar, conectar, organizar y utilizar **MonetDB** en modo *standalone* (autónomo) en un entorno Windows utilizando los scripts por lotes `.bat` y el conector de Python.

---

## 1. Inicio y Apagado del Servidor

### Iniciar el Servidor (`M5server.bat`)
El motor de la base de datos se ejecuta en segundo plano a través de este archivo.
1. Ve a la carpeta de instalación (por defecto: `C:\Program Files\MonetDB\MonetDB5`).
2. Haz doble clic en **`M5server.bat`**.
3. **Importante:** Se abrirá una ventana de la consola de Windows (CMD). **No la cierres**, ya que si lo haces apagarás el servidor. Por defecto, el sistema levantará una base de datos inicial llamada `demo`.

### Apagar el Servidor de forma segura
1. En la consola del cliente (`mclient`), escribe `\q` y pulsa Enter para desconectarte.
2. Ve a la ventana de `M5server.bat` y cierra la ventana haciendo clic en la `X` de la esquina superior derecha.

---

## 2. Conexión mediante el Cliente (`mclient.bat`)

Una vez que el servidor esté corriendo, puedes interactuar con él mediante la línea de comandos.
1. En la misma carpeta de instalación, haz doble clic en **`mclient.bat`**.
2. Introduce las credenciales por defecto cuando se te soliciten:
   * **Usuario:** `monetdb`
   * **Contraseña:** `monetdb`
3. Sabrás que estás dentro cuando el prompt de la consola cambie a `sql>`.

> ⚠️ **Regla de oro:** Todas las sentencias SQL ejecutadas en `mclient` **deben terminar en punto y coma (`;`)** para poder procesarse.

### Comandos útiles de la consola (Empiezan por `\`)
* `\?` : Muestra la ayuda en pantalla de los comandos internos del cliente.
* `\d` : Lista todas las tablas creadas por el usuario en la base de datos actual.
* `\d nombre_tabla` : Muestra la estructura (columnas y tipos de datos) de una tabla específica.
* `\q` : Cierra la sesión del cliente de forma segura (también puedes usar `Ctrl + C`).

---

## 3. Administración de Bases de Datos y Esquemas

En el modo *standalone*, **cada proceso del servidor corresponde exactamente a una sola base de datos activa**. No existe un comando SQL como `SHOW DATABASES;`.

### Localizar tus bases de datos (Físico)
MonetDB almacena los datos en una carpeta llamada **`dbfarm`** (usualmente en la ruta de instalación o en tu perfil de usuario). Cada subcarpeta dentro de `dbfarm` representa una base de datos física independiente (como la carpeta `demo`).

### Listar Esquemas existentes (Vía SQL)
Para ver los esquemas dentro de la base de datos a la que estás conectado, ejecuta en `mclient`:
```sql
SELECT name FROM sys.schemas;
-- O también usando el estándar ANSI:
SELECT schema_name FROM information_schema.schemata;
```

### Trabajar con Esquemas de Prueba
Para evitar mezclar tus datos con el esquema del sistema (`sys`), puedes crear un esquema propio:

1. **Crear el esquema:**
   ```sql
   CREATE SCHEMA prueba;
   ```
2. **Método A: Uso explícito con punto (Recomendado para scripts):**
   ```sql
   CREATE TABLE prueba.usuarios (id INT, nombre VARCHAR(50));
   INSERT INTO prueba.usuarios VALUES (1, 'Pedro');
   SELECT * FROM prueba.usuarios;
   ```
3. **Método B: Cambiar el entorno activo (Recomendado para consola):**
   ```sql
   SET SCHEMA prueba;
   -- Ahora las tablas se crean y consultan aquí directamente:
   CREATE TABLE productos (codigo INT, descripcion VARCHAR(100));
   SELECT * FROM productos;
   ```
4. **Volver al esquema principal:**
   ```sql
   SET SCHEMA sys;
   ```

---

## 4. Conexión desde Python (`pymonetdb`)

Para conectarte desde tus scripts de Python, debes especificar la base de datos (`demo`), pero **el esquema no se define en los parámetros de conexión**. Por defecto, entrarás a `sys`.

### Código de conexión estándar
```python
import pymonetdb

# Establecer la conexión con el servidor standalone
conn = pymonetdb.connect(
    username='monetdb',
    password='monetdb',
    hostname='localhost',
    port=50000,
    database='demo'  # Nombre de la carpeta/BD en tu dbfarm
)

cursor = conn.cursor()

# Ejemplo de consulta de verificación
cursor.execute("SELECT 'Conexión exitosa desde Python';")
print(cursor.fetchone())

cursor.close()
conn.close()
```

### Cambiar de esquema desde Python
Si has creado el esquema `prueba`, puedes trabajar con él de dos formas tras abrir tu cursor:

* **Opción 1 (Modificar el entorno):**
  ```python
  cursor.execute("SET SCHEMA prueba;")
  cursor.execute("SELECT * FROM productos;")
  ```
* **Opción 2 (Ruta explícita):**
  ```python
  cursor.execute("SELECT * FROM prueba.productos;")
  ```
## 5. Cheat Sheet: Comandos y Consultas más Comunes en MonetDB

Esta sección recopila las instrucciones esenciales para administrar esquemas, consultar metadatos del sistema y auditar el estado de tus tablas tras una migración.

### A. Inspección y Gestión de Tablas
*   **Listar todas las tablas de un esquema específico:**
    ```sql
    SELECT t.name 
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.id
    WHERE s.name = 'tu_nombre_de_esquema' 
      AND t.system = FALSE;
    ```
*   **Ver la definición y tipos de datos de una tabla (DDL):**
    ```sql
    -- Comando exclusivo de la consola mclient:
    \d nombre_de_tabla
    ```
*   **Contar filas de todas las tablas de un esquema automáticamente:**
    ```sql
    SELECT t.name AS tabla, t.count AS total_filas
    FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.id
    WHERE s.name = 'tu_nombre_de_esquema'
    ORDER BY t.count DESC;
    ```

### B. Análisis de Almacenamiento y Rendimiento
Al ser una base de datos columnar, el espacio se calcula a nivel de columnas.
*   **Ver el tamaño en disco de las tablas de tu esquema:**
    ```sql
    SELECT t.name AS tabla, 
           ROUND(SUM(c.imprintsize + c.dictsize + c.totalsize) / 1024.0 / 1024.0, 2) AS tamano_mb
    FROM sys.tables t
    JOIN sys.columns c ON t.id = c.table_id
    JOIN sys.schemas s ON t.schema_id = s.id
    WHERE s.name = 'tu_nombre_de_esquema'
    GROUP BY t.name
    ORDER BY tamano_mb DESC;
    ```
*   **Listar las consultas que se están ejecutando actualmente (Ver procesos activos):**
    ```sql
    SELECT sessionid, username, starttime, status, query 
    FROM sys.queue 
    WHERE status = 'running';
    ```

### C. Carga y Manipulación de Datos Masivos (Bulk Operations)
*   **Importar un archivo CSV local de forma ultra rápida (Bulk Load):**
    ```sql
    COPY INTO tu_esquema.tu_tabla 
    FROM 'C:/ruta/al/archivo.csv' 
    USING DELIMITERS ',', '\n', '"' 
    NULL AS '';
    ```
*   **Vaciar una tabla por completo de forma eficiente (Truncate):**
    ```sql
    TRUNCATE TABLE tu_esquema.tu_tabla;
    ```
*   **Eliminar una tabla y todas sus dependencias (Cascada):**
    ```sql
    DROP TABLE tu_esquema.tu_tabla CASCADE;
    ```

### D. Consultas del Sistema y Sesión
*   **Conocer la versión exacta de MonetDB instalada:**
    ```sql
    SELECT value FROM sys.env() WHERE name = 'monet_version';
    ```
*   **Saber qué usuario y esquema tienes activos en la sesión actual:**
    ```sql
    SELECT current_user, current_schema;
    ```