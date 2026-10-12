# Guía Rápida de Uso: Oracle Database local en Windows

Esta guía contiene los pasos esenciales para iniciar, conectar, organizar y utilizar **Oracle Database** en un entorno Windows local utilizando comandos del sistema, herramientas de línea de comandos y el conector de Python.

---

## 1. Inicio y Apagado del Servidor

### Iniciar el Servidor (Servicios de Windows)
A diferencia de MonetDB, Oracle se ejecuta como un conjunto de servicios nativos de Windows en segundo plano.
1. Abre el menú Inicio, busca **"Servicios"** (`services.msc`) y ábrelo.
2. Localiza los dos servicios críticos de Oracle (asumiendo la instancia por defecto `ORCL` o `XE` para Express Edition):
   * `OracleServiceORCL` (El motor de la base de datos)
   * `OracleOraDB21Home1TNSListener` (El escuchador para conexiones externas y Python)
3. Haz clic derecho sobre cada uno y selecciona **Iniciar**.

### Apagar el Servidor de forma segura
1. En la consola del cliente (`sqlplus`), escribe `EXIT;` para desconectarte.
2. Abre la herramienta de **Servicios** de Windows, haz clic derecho sobre `OracleServiceORCL` y selecciona **Detener**.

---

## 2. Conexión mediante el Cliente (`SQL*Plus`)

Una vez que los servicios estén corriendo, puedes interactuar con el motor mediante la herramienta oficial de línea de comandos.
1. Abre una consola de Windows (CMD) o PowerShell.
2. Ejecuta el comando para conectarte como administrador del sistema:
   ```bash
   sqlplus sys as sysdba
   ```
3. Introduce la contraseña de administrador configurada durante la instalación.
4. Sabrás que estás dentro cuando el prompt de la consola cambie a `SQL>`.

> ⚠️ **Regla de oro:** Todas las sentencias SQL ejecutadas en `SQL*Plus` **deben terminar en punto y coma (`;`)** o con una barra diagonal (`/`) en una nueva línea para poder procesarse.

### Comandos útiles de la consola (Comandos SQL*Plus)
* `HELP INDEX` : Muestra los temas de ayuda disponibles en la consola.
* `DESC nombre_tabla` : Muestra la estructura (columnas y tipos de datos) de una tabla específica.
* `CLEAR SCREEN` : Limpia el texto de la pantalla de la consola (o usa el alias `cl scr`).
* `EXIT` : Cierra la sesión del cliente de forma segura.

---

## 3. Administración de Bases de Datos y Esquemas

En Oracle, el concepto de **Esquema** equivale directamente a un **Usuario**. Al crear un usuario, el sistema crea automáticamente un esquema con el mismo nombre para almacenar sus tablas.

### Localizar tus bases de datos (Arquitectura CDB/PDB)
Las versiones modernas de Oracle utilizan una arquitectura de contenedor. Tienes una base de datos raíz (`CDB$ROOT`) y bases de datos conectables individuales (`PDB`). Puedes comprobar en cuál estás mediante:
```sql
SHOW CON_NAME;
```

### Listar Esquemas existentes (Vía SQL)
Los nombres de esquemas (usuarios) se guardan siempre en **mayúsculas**. Para ver los esquemas disponibles en el sistema:
```sql
SELECT username FROM all_users ORDER BY username;
```

### Trabajar con Esquemas de Prueba
Para evitar mezclar tus datos con los del sistema (`SYS` o `SYSTEM`), debes crear un usuario/esquema propio:

1. **Crear el esquema (usuario) y asignarle permisos:**
   ```sql
   -- Crear usuario de prueba (en CDB se suele requerir el prefijo C##)
   CREATE USER c##prueba IDENTIFIED BY tu_contraseña;
   -- Otorgar permisos básicos de conexión y creación de objetos
   GRANT CONNECT, RESOURCE, UNLIMITED TABLESPACE TO c##prueba;
   ```
2. **Método A: Uso explícito con punto (Recomendado para scripts):**
   ```sql
   CREATE TABLE c##prueba.usuarios (id NUMBER, nombre VARCHAR2(50));
   INSERT INTO c##prueba.usuarios VALUES (1, 'Pedro');
   SELECT * FROM c##prueba.usuarios;
   ```
3. **Método B: Cambiar el entorno activo (Recomendado para consola):**
   ```sql
   -- Cambia la sesión para que busque por defecto en el esquema de prueba
   ALTER SESSION SET CURRENT_SCHEMA = c##prueba;
   -- Ahora las tablas se crean y consultan aquí directamente:
   CREATE TABLE productos (codigo NUMBER, descripcion VARCHAR2(100));
   SELECT * FROM productos;
   ```

---

## 4. Conexión desde Python (`python-oracledb`)

Para conectarte desde tus scripts de Python, debes especificar las credenciales del esquema. Si tu base de datos utiliza un juego de caracteres nacionales antiguo (como `ID 871`), recuerda inicializar el **Modo Thick**.

### Código de conexión estándar
```python
import oracledb

# Opcional: Activar Modo Thick si usas NCHAR antiguo (ej. ID 871)
# oracledb.init_oracle_client(lib_dir=r"C:\oracle\instantclient_19_22")

# Establecer la conexión con el servidor Oracle
conn = oracledb.connect(
    user="c##prueba",
    password="tu_contraseña",
    dsn="localhost:1521/ORCL"  # Host:Puerto/NombreServicio o SID
)

cursor = conn.cursor()

# Ejemplo de consulta de verificación
cursor.execute("SELECT 'Conexión exitosa desde Python' FROM dual")
print(cursor.fetchone()[0])

cursor.close()
conn.close()
```

---

## 5. Cheat Sheet: Comandos y Consultas más Comunes en Oracle

Esta sección recopila las instrucciones esenciales para administrar esquemas, consultar metadatos del sistema y auditar el estado de tus tablas.

### A. Inspección y Gestión de Tablas
*   **Listar todas las tablas de un esquema específico:**
    ```sql
    SELECT table_name 
    FROM all_tables 
    WHERE owner = 'C##PRUEBA' 
    ORDER BY table_name;
    ```
*   **Buscar tablas que contengan una palabra específica en su nombre:**
    ```sql
    SELECT table_name 
    FROM all_tables 
    WHERE owner = 'C##PRUEBA' 
      AND UPPER(table_name) LIKE '%LOG%';
    ```
*   **Contar filas de todas las tablas de un esquema automáticamente:**
    ```sql
    SELECT table_name, num_rows 
    FROM all_tables 
    WHERE owner = 'C##PRUEBA' 
    ORDER BY num_rows DESC;
    -- Nota: 'num_rows' depende de que las estadísticas estén actualizadas.
    ```

### B. Análisis de Almacenamiento y Rendimiento
*   **Ver el tamaño en disco de las tablas de tu esquema:**
    ```sql
    SELECT segment_name AS tabla, 
           ROUND(SUM(bytes) / 1024 / 1024, 2) AS tamano_mb
    FROM user_segments
    WHERE segment_type = 'TABLE'
    GROUP BY segment_name
    ORDER BY tamano_mb DESC;
    ```
*   **Listar las consultas que se están ejecutando actualmente:**
    ```sql
    SELECT sid, serial#, username, status, sql_text 
    FROM v\$session s
    JOIN v\$sql q ON s.sql_hash_value = q.hash_value
    WHERE s.status = 'ACTIVE' AND s.username IS NOT NULL;
    ```

### C. Carga y Manipulación de Datos Masivos (Bulk Operations)
*   **Vaciar una tabla por completo liberando el espacio (Truncate):**
    ```sql
    TRUNCATE TABLE c##prueba.tu_tabla;
    ```
*   **Eliminar una tabla y todas sus restricciones de integridad (Cascada):**
    ```sql
    DROP TABLE c##prueba.tu_tabla CASCADE CONSTRAINTS;
    ```

### D. Consultas del Sistema y Sesión
*   **Conocer la versión exacta de Oracle Database instalada:**
    ```sql
    SELECT banner FROM v\$version;
    ```
*   **Saber qué usuario y esquema tienes activos en la sesión actual:**
    ```sql
    SELECT sys_context('USERENV', 'CURRENT_USER') AS usuario_actual,
           sys_context('USERENV', 'CURRENT_SCHEMA') AS esquema_actual 
    FROM dual;
    ```