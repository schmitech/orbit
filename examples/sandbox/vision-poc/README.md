# Receipt Processing POC

This project demonstrates how to extract receipt information from images using OpenAI's GPT-4 Vision API and store the data in a SQLite database.

Based on this article: https://medium.com/@alejandro7899871776/llms-sqlalchemy-pydantic-a-perfect-trio-8b68d9830aef

## Features

- Extract receipt data from images using GPT-4 Vision
- Store extracted data in SQLite database
- Support for multiple items per receipt
- Automatic categorization of receipts by type

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up environment variables:**
   ```bash
   cp env.example .env
   ```
   Then edit `.env` and add your OpenAI API key:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   ```

3. **Prepare your receipt image:**
   - Place your receipt image as `receipt.png` in the project directory
   - The image should be clear and readable

## Usage

Run the receipt processing script:
```bash
python receipt.py
```

## Expected Output

The script will:
1. Process the receipt image using GPT-4 Vision
2. Extract items, prices, and total amount
3. Categorize the receipt (e.g., Food, Tools, Transportation)
4. Store the data in a SQLite database
5. Display the stored receipt information

Example output:
```
Processing receipt image...

Stored receipts in database:

<DBReceipt(id=1, total=79.29, tag=Food, items=[<DBItem(item_id=1, name=300G SIRLOIN, price=38.0)>, <DBItem(item_id=2, name=400G T BONE, price=40.0)>])>
```

## Database Schema

- **receipts table**: Stores receipt metadata (id, total, tag)
- **items table**: Stores individual items (item_id, recipe_id, name, price)

## Dependencies

- `openai`: OpenAI API client
- `pydantic`: Data validation and serialization
- `python-dotenv`: Environment variable management
- `sqlalchemy`: Database ORM

## Notes

- The script uses GPT-4o-mini for cost efficiency
- The database file (`receipt.db`) will be created automatically
- Each run will add new receipts to the database 