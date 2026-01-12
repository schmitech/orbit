-- Library Management System Database Schema
-- A simple but comprehensive SQLite schema for testing template generation

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- Create authors table
CREATE TABLE IF NOT EXISTS authors (
    author_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    birth_date DATE,
    nationality TEXT,
    biography TEXT,
    website TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create categories table
CREATE TABLE IF NOT EXISTS categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    parent_category_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_category_id) REFERENCES categories(category_id)
);

-- Create publishers table
CREATE TABLE IF NOT EXISTS publishers (
    publisher_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    address TEXT,
    city TEXT,
    country TEXT,
    phone TEXT,
    email TEXT,
    website TEXT,
    founded_year INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create books table
CREATE TABLE IF NOT EXISTS books (
    book_id INTEGER PRIMARY KEY AUTOINCREMENT,
    isbn TEXT UNIQUE,
    title TEXT NOT NULL,
    subtitle TEXT,
    description TEXT,
    publication_date DATE,
    pages INTEGER,
    language TEXT DEFAULT 'English',
    edition TEXT,
    price DECIMAL(10, 2),
    publisher_id INTEGER,
    category_id INTEGER,
    is_available INTEGER DEFAULT 1 CHECK (is_available IN (0, 1)),
    total_copies INTEGER DEFAULT 1,
    available_copies INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (publisher_id) REFERENCES publishers(publisher_id),
    FOREIGN KEY (category_id) REFERENCES categories(category_id)
);

-- Create book_authors junction table (many-to-many)
CREATE TABLE IF NOT EXISTS book_authors (
    book_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    role TEXT DEFAULT 'author', -- author, co-author, editor, translator
    PRIMARY KEY (book_id, author_id),
    FOREIGN KEY (book_id) REFERENCES books(book_id) ON DELETE CASCADE,
    FOREIGN KEY (author_id) REFERENCES authors(author_id) ON DELETE CASCADE
);

-- Create members table
CREATE TABLE IF NOT EXISTS members (
    member_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    address TEXT,
    city TEXT,
    postal_code TEXT,
    membership_type TEXT DEFAULT 'standard' CHECK (membership_type IN ('standard', 'premium', 'student', 'senior')),
    membership_start_date DATE DEFAULT CURRENT_DATE,
    membership_end_date DATE,
    is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Create loans table
CREATE TABLE IF NOT EXISTS loans (
    loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    loan_date DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date DATE NOT NULL,
    return_date DATE,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'returned', 'overdue', 'lost')),
    fine_amount DECIMAL(10, 2) DEFAULT 0.00,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books(book_id),
    FOREIGN KEY (member_id) REFERENCES members(member_id)
);

-- Create reservations table
CREATE TABLE IF NOT EXISTS reservations (
    reservation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    reservation_date DATE NOT NULL DEFAULT CURRENT_DATE,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'fulfilled', 'cancelled', 'expired')),
    priority INTEGER DEFAULT 1,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books(book_id),
    FOREIGN KEY (member_id) REFERENCES members(member_id)
);

-- Create reviews table
CREATE TABLE IF NOT EXISTS reviews (
    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id INTEGER NOT NULL,
    member_id INTEGER NOT NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    review_text TEXT,
    is_verified INTEGER DEFAULT 0 CHECK (is_verified IN (0, 1)),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id) REFERENCES books(book_id),
    FOREIGN KEY (member_id) REFERENCES members(member_id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_isbn ON books(isbn);
CREATE INDEX IF NOT EXISTS idx_books_category ON books(category_id);
CREATE INDEX IF NOT EXISTS idx_books_publisher ON books(publisher_id);
CREATE INDEX IF NOT EXISTS idx_books_publication_date ON books(publication_date);
CREATE INDEX IF NOT EXISTS idx_books_available ON books(is_available);

CREATE INDEX IF NOT EXISTS idx_authors_name ON authors(last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_authors_nationality ON authors(nationality);

CREATE INDEX IF NOT EXISTS idx_members_email ON members(email);
CREATE INDEX IF NOT EXISTS idx_members_name ON members(last_name, first_name);
CREATE INDEX IF NOT EXISTS idx_members_membership_type ON members(membership_type);
CREATE INDEX IF NOT EXISTS idx_members_active ON members(is_active);

CREATE INDEX IF NOT EXISTS idx_loans_book ON loans(book_id);
CREATE INDEX IF NOT EXISTS idx_loans_member ON loans(member_id);
CREATE INDEX IF NOT EXISTS idx_loans_status ON loans(status);
CREATE INDEX IF NOT EXISTS idx_loans_due_date ON loans(due_date);
CREATE INDEX IF NOT EXISTS idx_loans_loan_date ON loans(loan_date);

CREATE INDEX IF NOT EXISTS idx_reservations_book ON reservations(book_id);
CREATE INDEX IF NOT EXISTS idx_reservations_member ON reservations(member_id);
CREATE INDEX IF NOT EXISTS idx_reservations_status ON reservations(status);

CREATE INDEX IF NOT EXISTS idx_reviews_book ON reviews(book_id);
CREATE INDEX IF NOT EXISTS idx_reviews_member ON reviews(member_id);
CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews(rating);

-- Create triggers for updated_at timestamps
CREATE TRIGGER IF NOT EXISTS update_authors_timestamp 
    AFTER UPDATE ON authors
    FOR EACH ROW
    BEGIN
        UPDATE authors SET updated_at = CURRENT_TIMESTAMP WHERE author_id = NEW.author_id;
    END;

CREATE TRIGGER IF NOT EXISTS update_books_timestamp 
    AFTER UPDATE ON books
    FOR EACH ROW
    BEGIN
        UPDATE books SET updated_at = CURRENT_TIMESTAMP WHERE book_id = NEW.book_id;
    END;

CREATE TRIGGER IF NOT EXISTS update_members_timestamp 
    AFTER UPDATE ON members
    FOR EACH ROW
    BEGIN
        UPDATE members SET updated_at = CURRENT_TIMESTAMP WHERE member_id = NEW.member_id;
    END;

CREATE TRIGGER IF NOT EXISTS update_loans_timestamp 
    AFTER UPDATE ON loans
    FOR EACH ROW
    BEGIN
        UPDATE loans SET updated_at = CURRENT_TIMESTAMP WHERE loan_id = NEW.loan_id;
    END;

CREATE TRIGGER IF NOT EXISTS update_reviews_timestamp 
    AFTER UPDATE ON reviews
    FOR EACH ROW
    BEGIN
        UPDATE reviews SET updated_at = CURRENT_TIMESTAMP WHERE review_id = NEW.review_id;
    END;

-- Insert sample data
INSERT OR IGNORE INTO categories (name, description) VALUES
    ('Fiction', 'Fictional literature including novels, short stories, and poetry'),
    ('Non-Fiction', 'Factual and informational books'),
    ('Science Fiction', 'Speculative fiction dealing with futuristic concepts'),
    ('Mystery', 'Books involving crime, detective work, and suspense'),
    ('Romance', 'Books focusing on romantic relationships'),
    ('Biography', 'Accounts of people''s lives written by others'),
    ('History', 'Books about historical events and periods'),
    ('Science', 'Books about scientific topics and discoveries'),
    ('Technology', 'Books about computers, software, and digital technology'),
    ('Self-Help', 'Books designed to help readers improve themselves');

INSERT OR IGNORE INTO publishers (name, address, city, country, phone, email, website, founded_year) VALUES
    ('Penguin Random House', '1745 Broadway', 'New York', 'USA', '+1-212-782-9000', 'info@penguinrandomhouse.com', 'https://www.penguinrandomhouse.com', 2013),
    ('HarperCollins', '195 Broadway', 'New York', 'USA', '+1-212-207-7000', 'info@harpercollins.com', 'https://www.harpercollins.com', 1987),
    ('Simon & Schuster', '1230 Avenue of the Americas', 'New York', 'USA', '+1-212-698-7000', 'info@simonandschuster.com', 'https://www.simonandschuster.com', 1924),
    ('Macmillan Publishers', '120 Broadway', 'New York', 'USA', '+1-646-307-5151', 'info@macmillan.com', 'https://www.macmillan.com', 1843),
    ('Hachette Book Group', '1290 Avenue of the Americas', 'New York', 'USA', '+1-212-364-1100', 'info@hachettebookgroup.com', 'https://www.hachettebookgroup.com', 2006);

INSERT OR IGNORE INTO authors (first_name, last_name, birth_date, nationality, biography, website) VALUES
    ('George', 'Orwell', '1903-06-25', 'British', 'Eric Arthur Blair, known by his pen name George Orwell, was an English novelist, essayist, journalist, and critic.', 'https://www.georgeorwell.org'),
    ('J.K.', 'Rowling', '1965-07-31', 'British', 'Joanne Rowling, known by her pen name J.K. Rowling, is a British author, philanthropist, film producer, television producer, and screenwriter.', 'https://www.jkrowling.com'),
    ('Isaac', 'Asimov', '1920-01-02', 'American', 'Isaac Asimov was an American writer and professor of biochemistry at Boston University.', 'https://www.asimovonline.com'),
    ('Agatha', 'Christie', '1890-09-15', 'British', 'Dame Agatha Christie was an English writer known for her 66 detective novels and 14 short story collections.', 'https://www.agathachristie.com'),
    ('Stephen', 'King', '1947-09-21', 'American', 'Stephen Edwin King is an American author of horror, supernatural fiction, suspense, crime, science-fiction, and fantasy novels.', 'https://www.stephenking.com'),
    ('Jane', 'Austen', '1775-12-16', 'British', 'Jane Austen was an English novelist known primarily for her six major novels.', 'https://www.janeausten.org'),
    ('Charles', 'Darwin', '1809-02-12', 'British', 'Charles Robert Darwin was an English naturalist, geologist and biologist, best known for his contributions to the science of evolution.', NULL),
    ('Albert', 'Einstein', '1879-03-14', 'German-American', 'Albert Einstein was a German-born theoretical physicist who developed the theory of relativity.', NULL);

INSERT OR IGNORE INTO books (isbn, title, subtitle, description, publication_date, pages, language, edition, price, publisher_id, category_id, total_copies, available_copies) VALUES
    ('978-0-452-28423-4', '1984', NULL, 'A dystopian social science fiction novel and cautionary tale about the dangers of totalitarianism.', '1949-06-08', 328, 'English', '1st', 12.99, 1, 1, 3, 2),
    ('978-0-439-13959-7', 'Harry Potter and the Philosopher''s Stone', NULL, 'The first novel in the Harry Potter series and Rowling''s debut novel.', '1997-06-26', 223, 'English', '1st', 8.99, 2, 1, 5, 3),
    ('978-0-553-29335-5', 'Foundation', NULL, 'The first book in Isaac Asimov''s Foundation series.', '1951-05-01', 244, 'English', '1st', 7.99, 3, 3, 2, 1),
    ('978-0-06-207348-8', 'Murder on the Orient Express', NULL, 'A detective novel featuring Hercule Poirot.', '1934-01-01', 256, 'English', '1st', 9.99, 2, 4, 4, 2),
    ('978-0-385-12167-5', 'The Shining', NULL, 'A horror novel about a family''s winter stay at an isolated hotel.', '1977-01-28', 447, 'English', '1st', 15.99, 4, 1, 2, 1),
    ('978-0-14-143951-8', 'Pride and Prejudice', NULL, 'A romantic novel of manners written by Jane Austen.', '1813-01-28', 432, 'English', '1st', 6.99, 1, 5, 3, 2),
    ('978-0-14-143951-8', 'On the Origin of Species', 'By Means of Natural Selection', 'A work of scientific literature by Charles Darwin.', '1859-11-24', 502, 'English', '1st', 11.99, 1, 2, 1, 1),
    ('978-0-517-88436-9', 'Relativity: The Special and General Theory', NULL, 'Einstein''s own explanation of his theory of relativity.', '1916-01-01', 165, 'English', '1st', 9.99, 5, 2, 1, 1);

INSERT OR IGNORE INTO book_authors (book_id, author_id, role) VALUES
    (1, 1, 'author'),
    (2, 2, 'author'),
    (3, 3, 'author'),
    (4, 4, 'author'),
    (5, 5, 'author'),
    (6, 6, 'author'),
    (7, 7, 'author'),
    (8, 8, 'author');

INSERT OR IGNORE INTO members (first_name, last_name, email, phone, address, city, postal_code, membership_type, membership_start_date, membership_end_date) VALUES
    ('John', 'Smith', 'john.smith@email.com', '+1-555-0101', '123 Main St', 'New York', '10001', 'premium', '2023-01-15', '2024-01-15'),
    ('Sarah', 'Johnson', 'sarah.johnson@email.com', '+1-555-0102', '456 Oak Ave', 'Los Angeles', '90210', 'standard', '2023-03-20', '2024-03-20'),
    ('Michael', 'Brown', 'michael.brown@email.com', '+1-555-0103', '789 Pine St', 'Chicago', '60601', 'student', '2023-09-01', '2024-05-31'),
    ('Emily', 'Davis', 'emily.davis@email.com', '+1-555-0104', '321 Elm St', 'Boston', '02101', 'senior', '2022-11-10', '2023-11-10'),
    ('David', 'Wilson', 'david.wilson@email.com', '+1-555-0105', '654 Maple Dr', 'Seattle', '98101', 'premium', '2023-06-01', '2024-06-01');

INSERT OR IGNORE INTO loans (book_id, member_id, loan_date, due_date, return_date, status, fine_amount) VALUES
    (1, 1, '2024-01-10', '2024-01-24', NULL, 'active', 0.00),
    (2, 2, '2024-01-12', '2024-01-26', NULL, 'active', 0.00),
    (3, 3, '2024-01-05', '2024-01-19', '2024-01-18', 'returned', 0.00),
    (4, 4, '2023-12-15', '2023-12-29', NULL, 'overdue', 2.50),
    (5, 5, '2024-01-08', '2024-01-22', NULL, 'active', 0.00);

INSERT OR IGNORE INTO reservations (book_id, member_id, reservation_date, status, priority) VALUES
    (1, 2, '2024-01-15', 'pending', 1),
    (3, 4, '2024-01-20', 'pending', 2),
    (6, 1, '2024-01-18', 'pending', 1);

INSERT OR IGNORE INTO reviews (book_id, member_id, rating, review_text, is_verified) VALUES
    (1, 1, 5, 'A masterpiece of dystopian fiction. Still relevant today.', 1),
    (2, 2, 5, 'Magical and enchanting. Perfect for all ages.', 1),
    (3, 3, 4, 'Classic science fiction. Asimov at his best.', 1),
    (4, 4, 5, 'Brilliant mystery with an unexpected ending.', 1),
    (5, 5, 4, 'Terrifying and atmospheric. King''s horror masterpiece.', 1);

-- Create views for common queries
CREATE VIEW IF NOT EXISTS book_summary AS
SELECT 
    b.book_id,
    b.isbn,
    b.title,
    b.subtitle,
    b.publication_date,
    b.pages,
    b.price,
    b.total_copies,
    b.available_copies,
    c.name as category_name,
    p.name as publisher_name,
    GROUP_CONCAT(a.first_name || ' ' || a.last_name, ', ') as authors
FROM books b
LEFT JOIN categories c ON b.category_id = c.category_id
LEFT JOIN publishers p ON b.publisher_id = p.publisher_id
LEFT JOIN book_authors ba ON b.book_id = ba.book_id
LEFT JOIN authors a ON ba.author_id = a.author_id
GROUP BY b.book_id;

CREATE VIEW IF NOT EXISTS member_summary AS
SELECT 
    m.member_id,
    m.first_name,
    m.last_name,
    m.email,
    m.membership_type,
    m.is_active,
    COUNT(l.loan_id) as total_loans,
    COUNT(CASE WHEN l.status = 'active' THEN 1 END) as active_loans,
    COUNT(CASE WHEN l.status = 'overdue' THEN 1 END) as overdue_loans
FROM members m
LEFT JOIN loans l ON m.member_id = l.member_id
GROUP BY m.member_id;

CREATE VIEW IF NOT EXISTS loan_summary AS
SELECT 
    l.loan_id,
    l.loan_date,
    l.due_date,
    l.return_date,
    l.status,
    l.fine_amount,
    b.title as book_title,
    b.isbn,
    m.first_name || ' ' || m.last_name as member_name,
    m.email as member_email
FROM loans l
LEFT JOIN books b ON l.book_id = b.book_id
LEFT JOIN members m ON l.member_id = m.member_id;
