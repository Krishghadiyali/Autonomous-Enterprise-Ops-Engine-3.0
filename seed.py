import os
import time
import hashlib
import mysql.connector
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from app.db.database import get_db_connection

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_PATH = os.path.join(BASE_DIR, "Company_policy.pdf")
CHROMA_PATH = os.path.join(BASE_DIR, "chroma_db")


def hash_password(plain_password: str) -> str:
    """Creates a deterministic SHA-256 hash for seeded user passwords."""
    return hashlib.sha256(plain_password.encode("utf-8")).hexdigest()


def wait_for_database(max_retries: int = 15, delay_seconds: int = 3):
    """Ensures MySQL is ready and the target database exists before creating tables."""
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = int(os.getenv("DB_PORT", "3306"))
    db_user = os.getenv("DB_USER", "root")
    db_password = os.getenv("DB_PASS")
    db_name = os.getenv("DB_NAME")

    for attempt in range(1, max_retries + 1):
        try:
            conn = mysql.connector.connect(
                host=db_host, port=db_port, user=db_user, password=db_password
            )
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`;")
            cursor.close()
            conn.close()
            return
        except mysql.connector.Error as err:
            print(f"Waiting for MySQL ({attempt}/{max_retries})... ({err})")
            time.sleep(delay_seconds)
    raise RuntimeError("Could not connect to MySQL after maximum retries.")


def _safe_add_column(cursor, table: str, column_def: str):
    """Safely adds new columns to existing tables if upgrading an existing volume."""
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
    except mysql.connector.Error:
        pass


def seed_database():
    """Creates MySQL tables with authentication columns and seeds demo customers & orders."""
    wait_for_database()
    conn = get_db_connection()
    cursor = conn.cursor()

    print("Creating/Upgrading MySQL tables...")

    # 1. Create Customers Table (with password_hash and role for Phase 1 Security)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            id INT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) DEFAULT 'customer'
        )
        """
    )
    _safe_add_column(cursor, "customers", "password_hash VARCHAR(255) NOT NULL DEFAULT ''")
    _safe_add_column(cursor, "customers", "role VARCHAR(50) DEFAULT 'customer'")

    # 2. Create Orders Table (with item_name so users don't need to memorize order IDs)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INT PRIMARY KEY,
            customer_id INT NOT NULL,
            item_name VARCHAR(255) DEFAULT 'Standard Enterprise Order',
            total_amount DECIMAL(10, 2) NOT NULL,
            status VARCHAR(50) NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id)
        )
        """
    )
    _safe_add_column(
        cursor, "orders", "item_name VARCHAR(255) DEFAULT 'Standard Enterprise Order'"
    )

    # 3. Create Refunds Table (with UNIQUE constraint on order_id for idempotency)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS refunds (
            refund_id INT AUTO_INCREMENT PRIMARY KEY,
            order_id INT NOT NULL UNIQUE,
            refund_amount DECIMAL(10, 2) NOT NULL,
            reason TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )
        """
    )

    print("Inserting/Updating authenticated demo users and orders...")

    # Demo Accounts:
    # 1. Alice Smith: alice@example.com / alice123
    # 2. Bob Jones:   bob@example.com   / bob123
    # 3. Admin User:  admin@example.com / admin123
    users = [
        (1, "Alice Smith", "alice@example.com", hash_password("alice123"), "customer"),
        (2, "Bob Jones", "bob@example.com", hash_password("bob123"), "customer"),
        (99, "Enterprise Admin", "admin@example.com", hash_password("admin123"), "admin"),
    ]
    cursor.executemany(
        """
        INSERT INTO customers (id, name, email, password_hash, role)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            email = VALUES(email),
            password_hash = VALUES(password_hash),
            role = VALUES(role)
        """,
        users,
    )

    orders = [
        (999, 1, "Wireless Noise-Cancelling Headphones", 50.00, "delivered"),
        (404, 1, "Enterprise Workstation Monitor", 1200.00, "processing"),
        (555, 2, "Mechanical Keyswitch Developer Keyboard", 150.00, "delivered"),
    ]
    cursor.executemany(
        """
        INSERT INTO orders (id, customer_id, item_name, total_amount, status)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            item_name = VALUES(item_name),
            total_amount = VALUES(total_amount)
        """,
        orders,
    )

    conn.commit()
    cursor.close()
    conn.close()
    print("MySQL database seeded successfully with Phase 1 Security accounts!")


def seed_company_policy_pdf():
    """Loads Company_policy.pdf, chunks it, and embeds it into ChromaDB using HuggingFace."""
    if not os.path.exists(PDF_PATH):
        raise FileNotFoundError(f"Could not find policy PDF at: {PDF_PATH}")

    print("Checking ChromaDB 'company_policies' collection...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    vectorstore = Chroma(
        collection_name="company_policies",
        embedding_function=embeddings,
        persist_directory=CHROMA_PATH,
    )

    existing_docs = vectorstore.get()
    if existing_docs and len(existing_docs.get("ids", [])) > 0:
        print(
            f"ChromaDB already contains {len(existing_docs['ids'])} chunks from Company_policy.pdf. Skipping."
        )
        return

    print(f"Loading and chunking {PDF_PATH}...")
    loader = PyPDFLoader(PDF_PATH)
    raw_documents = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = text_splitter.split_documents(raw_documents)

    vectorstore.add_documents(chunks)
    print(
        f"Successfully embedded {len(chunks)} chunks from Company_policy.pdf into ChromaDB!"
    )


if __name__ == "__main__":
    seed_database()
    seed_company_policy_pdf()