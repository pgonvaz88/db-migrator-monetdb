# Guía de Conexión y Pruebas a Contenedores Locales (PostgreSQL & MonetDB)

Esta guía detalla cómo conectarse a los contenedores locales de **PostgreSQL** y **MonetDB** desplegados mediante Docker, incluyendo parámetros de conexión, acceso desde herramientas visuales (DBeaver, DataGrip), consolas interactivas por terminal y verificación programática mediante Python.

---

## 1. Parámetros de Conexión

| Parámetro | 🐘 PostgreSQL (Origen de pruebas) | 📊 MonetDB (Destino analítico) |
| :--- | :--- | :--- |
| **Contenedor Docker** | `migration_postgres` | `migration_monetdb` |
| **Host** | `localhost` (o `127.0.0.1`) | `localhost` (o `127.0.0.1`) |
| **Puerto en Host** | **`5433`** *(mapeado a 5432 interno)* | **`50000`** |
| **Base de Datos** | `django_postgres_db` | `demo` *(o `monetdb`)* |
| **Usuario** | `postgres` | `monetdb` |
| **Contraseña** | `postgres` | `monetdb` |
| **Esquema por defecto** | `public` | `sys` *(o el esquema migrado: `migrated`)* |

> ⚠️ **Nota sobre el puerto de PostgreSQL**: Se ha configurado el puerto **`5433`** en la máquina anfitriona para evitar colisiones con cualquier instancia de PostgreSQL instalada localmente en el puerto estándar `5432`.

---

## 2. Gestión de Contenedores

Para iniciar o verificar el estado de los servicios:

```bash
# Iniciar contenedores en segundo plano
docker compose up -d

# O usando el script de conveniencia
scripts\start_databases.bat

# Comprobar estado y salud de los contenedores
docker ps

# Ver logs de un contenedor
docker logs -f migration_postgres
docker logs -f migration_monetdb

# Detener los contenedores
docker compose down
```

---

## 3. Conexión desde Herramientas Gráficas (GUI)

### A. DBeaver

#### Conexión a PostgreSQL:
1. Menú **Base de datos** ➔ **Nueva conexión** ➔ Selecciona **PostgreSQL**.
2. Configura los campos:
   - **Host**: `localhost`
   - **Puerto**: `5433`
   - **Base de datos**: `django_postgres_db`
   - **Usuario**: `postgres`
   - **Contraseña**: `postgres`
3. Haz clic en **Probar conexión** y luego en **Finalizar**.

#### Conexión a MonetDB:
1. Menú **Base de datos** ➔ **Nueva conexión** ➔ Selecciona **MonetDB** *(si DBeaver solicita descargar el driver JDBC, acepta la descarga automática)*.
2. Configura los campos:
   - **Host**: `localhost`
   - **Puerto**: `50000`
   - **Base de datos**: `demo`
   - **Usuario**: `monetdb`
   - **Contraseña**: `monetdb`
3. Haz clic en **Probar conexión** y luego en **Finalizar**.

---

## 4. Conexión por Terminal (Docker CLI)

Puedes abrir una sesión interactiva directamente dentro de cada contenedor sin necesidad de instalar clientes en tu máquina.

### A. Terminal interactiva en PostgreSQL (`psql`)

```bash
docker exec -it migration_postgres psql -U postgres -d django_postgres_db
```

#### Comandos útiles en `psql`:
- `\dt` : Listar todas las tablas del esquema actual.
- `\dt+` : Listar tablas con su tamaño en disco.
- `\d nombre_tabla` : Ver columnas, tipos de datos e índices de una tabla.
- `\dn` : Listar esquemas disponibles.
- `SELECT count(*) FROM nombre_tabla;` : Contar registros de una tabla.
- `\q` : Salir de la consola.

---

### B. Terminal interactiva en MonetDB (`mclient`)

```bash
docker exec -it migration_monetdb mclient -u monetdb -d demo
```
*(Solicitará la contraseña: introduce `monetdb` y pulsa Enter)*.

#### Comandos útiles en `mclient`:
- `\d` : Listar tablas y vistas.
- `\d nombre_tabla` : Ver la definición DDL de una tabla.
- `\dn` : Listar esquemas.
- `SELECT * FROM nombre_tabla LIMIT 10;` : Consultar registros con límite.
- `SELECT count(*) FROM nombre_tabla;` : Contar filas en motor columnar.
- `\q` : Salir de la consola.

---

## 5. Pruebas Programáticas desde Python (`.venv`)

Asegúrate de tener el entorno virtual activado o utiliza el ejecutable de `.venv`.

### Test Rápido desde la Terminal (One-Liner)

Ejecuta en PowerShell:

```powershell
.venv\Scripts\python.exe -c "
import psycopg, pymonetdb

# 1. Probar PostgreSQL
try:
    with psycopg.connect('host=localhost port=5433 dbname=django_postgres_db user=postgres password=postgres') as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT version();')
            print('✅ PostgreSQL OK:', cur.fetchone()[0][:35])
except Exception as e:
    print('❌ Error PostgreSQL:', e)

# 2. Probar MonetDB
try:
    conn_m = pymonetdb.connect(hostname='localhost', port=50000, database='demo', username='monetdb', password='monetdb')
    cur_m = conn_m.cursor()
    cur_m.execute('SELECT 1;')
    print('✅ MonetDB OK (db demo):', cur_m.fetchall())
except Exception as e:
    print('❌ Error MonetDB:', e)
"
```

---

### Ejemplo de Script Python para Crear y Consultar Datos

Puedes crear un script temporal de prueba como el siguiente:

```python
import psycopg
import pymonetdb

# Conexión a Postgres
pg_conn = psycopg.connect(
    host="localhost",
    port=5433,
    dbname="django_postgres_db",
    user="postgres",
    password="postgres"
)

# Conexión a MonetDB
monet_conn = pymonetdb.connect(
    hostname="localhost",
    port=50000,
    database="demo",
    username="monetdb",
    password="monetdb"
)

# Crear tabla de prueba en MonetDB
with monet_conn.cursor() as cur:
    cur.execute("CREATE TABLE IF NOT EXISTS test_table (id INT, name VARCHAR(50));")
    cur.execute("INSERT INTO test_table VALUES (1, 'Prueba MonetDB');")
    monet_conn.commit()

    cur.execute("SELECT * FROM test_table;")
    print("Filas en MonetDB:", cur.fetchall())

pg_conn.close()
monet_conn.close()
```

---

## 6. Resolución de Problemas Comunes

1. **Error: `monetdbd: no such database 'demo'`**:
   Si la base de datos `demo` no existiese, se puede inicializar dentro del contenedor con:
   ```bash
   docker exec migration_monetdb monetdb create demo
   docker exec migration_monetdb monetdb release demo
   ```
2. **Error de conexión a PostgreSQL en puerto 5432**:
   Recuerda que desde tu máquina anfitriona debes apuntar al puerto **`5433`**, no al `5432`.
3. **El contenedor aparece como `unhealthy`**:
   Verifica los logs detallados con:
   ```bash
   docker logs migration_postgres
   docker logs migration_monetdb
   ```
