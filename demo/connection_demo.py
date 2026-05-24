import psycopg2
from langchain_core.tools import tool
from config.settings import get_settings

@tool
def connect_to_database() -> str:
    """Connect to the database and read the database schema"""
    try:
        database_settings = get_settings().database
        print(database_settings.get_params)
        connection = psycopg2.connect(
            host=database_settings.host,
            port=database_settings.port,
            dbname=database_settings.db,
            user=database_settings.user,
            password=database_settings.password
        )
        cursor = connection.cursor() 
        query = """
            SELECT * FROM test_connection LIMIT 1;
        """
        cursor.execute(query)
        results = cursor.fetchone()
        cursor.close()
        connection.close()
        if not results:
            return "Table is empty or missing"
        return results
    except Exception as e:
        return f"Connection failed: {e}"

def main():
    print("Connecting to database...")
    result = connect_to_database.invoke({})
    print(result)

if __name__ == "__main__":
    main()