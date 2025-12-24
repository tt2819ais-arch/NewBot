import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_file='bot.db'):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        # Пользователи
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                username TEXT,
                full_name TEXT,
                role TEXT DEFAULT 'user',
                card_number TEXT,
                account_number TEXT,
                phone_number TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Транзакции
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER,
                phone_number TEXT,
                amount INTEGER,
                bank TEXT,
                email TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES users (id)
            )
        ''')
        
        # Сессии
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER,
                target_amount INTEGER,
                current_amount INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES users (id)
            )
        ''')
        
        self.conn.commit()
    
    # Методы для работы с пользователями
    def add_user(self, user_id, username, full_name, role='user'):
        self.cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, full_name, role) 
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, full_name, role))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_user(self, user_id):
        self.cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        return self.cursor.fetchone()
    
    def update_user_role(self, user_id, role):
        self.cursor.execute('UPDATE users SET role = ? WHERE user_id = ?', (role, user_id))
        self.conn.commit()
    
    def get_all_users(self):
        self.cursor.execute('SELECT * FROM users WHERE role IN ("admin", "agent")')
        return self.cursor.fetchall()
    
    def get_agents(self):
        self.cursor.execute('SELECT * FROM users WHERE role = "agent" AND is_active = 1')
        return self.cursor.fetchall()
    
    def delete_agent(self, user_id):
        self.cursor.execute('DELETE FROM users WHERE user_id = ? AND role = "agent"', (user_id,))
        self.conn.commit()
    
    def delete_all_agents(self):
        self.cursor.execute('DELETE FROM users WHERE role = "agent"')
        self.conn.commit()
    
    # Методы для транзакций
    def add_transaction(self, agent_id, phone, amount, bank, email):
        self.cursor.execute('''
            INSERT INTO transactions (agent_id, phone_number, amount, bank, email)
            VALUES (?, ?, ?, ?, ?)
        ''', (agent_id, phone, amount, bank, email))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_transactions(self, agent_id=None):
        if agent_id:
            self.cursor.execute('SELECT * FROM transactions WHERE agent_id = ? ORDER BY timestamp DESC', (agent_id,))
        else:
            self.cursor.execute('SELECT * FROM transactions ORDER BY timestamp DESC')
        return self.cursor.fetchall()
    
    # Методы для сессий
    def create_session(self, agent_id, target_amount):
        # Деактивируем старые сессии
        self.cursor.execute('UPDATE sessions SET is_active = 0 WHERE agent_id = ?', (agent_id,))
        
        self.cursor.execute('''
            INSERT INTO sessions (agent_id, target_amount, current_amount, is_active)
            VALUES (?, ?, 0, 1)
        ''', (agent_id, target_amount))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_active_session(self, agent_id):
        self.cursor.execute('SELECT * FROM sessions WHERE agent_id = ? AND is_active = 1', (agent_id,))
        return self.cursor.fetchone()
    
    def update_session_amount(self, session_id, amount):
        self.cursor.execute('''
            UPDATE sessions SET current_amount = current_amount + ? 
            WHERE id = ?
        ''', (amount, session_id))
        self.conn.commit()
    
    def stop_session(self, session_id):
        self.cursor.execute('''
            UPDATE sessions SET is_active = 0, end_time = CURRENT_TIMESTAMP 
            WHERE id = ?
        ''', (session_id,))
        self.conn.commit()
    
    def close(self):
        self.conn.close()

# Глобальный экземпляр базы данных
db = Database()
