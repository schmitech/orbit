import base64
from pydantic import BaseModel, Field
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime

from sqlalchemy import create_engine, ForeignKey, select, delete
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped, relationship, sessionmaker

load_dotenv()
client = OpenAI()


class Recipe(BaseModel):
    items: list["Item"]
    total: float = Field(..., description="Total amount of the receipt")
    tag: str = Field(..., description="Single word describing the type of purchase (e.g., Food, Tools, Transportation)")


class Item(BaseModel):
    name: str = Field(..., description="Name should not have any special characters")
    price: float = Field(..., description="Price of the item")


def encode_image(image_path: str) -> str:
    """Encode an image to base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def generate_response(image_path: str, response_format: BaseModel):
    return client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Extract the data from the receipt"},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Help me extract the receipt information from the following image",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encode_image(image_path)}"
                        },
                    },
                ],
            },
        ],
        response_format=response_format,
    )


def clear_database(session):
    """Delete all existing records from the database."""
    print("🗑️  Clearing existing records from database...")
    session.execute(delete(DBItem))
    session.execute(delete(DBReceipt))
    session.commit()
    print("✅ Database cleared successfully.")


db_path = "sqlite:///receipt.db"
engine = create_engine(db_path)


class Base(DeclarativeBase):
    pass


class DBReceipt(Base):
    __tablename__ = "receipts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    total: Mapped[float] = mapped_column()
    tag: Mapped[str] = mapped_column()

    # Establish a bidirectional relationship with DBItem
    items: Mapped[list["DBItem"]] = relationship("DBItem", back_populates="receipt")

    def __repr__(self):
        return f"<DBReceipt(id={self.id}, total={self.total}, tag={self.tag}, items={self.items})>"
    
    def pretty_print(self):
        """Pretty print the receipt with formatting."""
        print("=" * 60)
        print(f"🧾 RECEIPT #{self.id:03d}")
        print("=" * 60)
        print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🏷️  Category: {self.tag}")
        print("-" * 60)
        print("📋 ITEMS:")
        print("-" * 60)
        
        total_items = 0
        subtotal = 0
        for item in self.items:
            print(f"  • {item.name:<30} ${item.price:>8.2f}")
            total_items += 1
            subtotal += item.price
        
        print("-" * 60)
        print(f"📊 Total Items: {total_items}")
        print(f"💵 Subtotal:     ${subtotal:>8.2f}")
        if abs(subtotal - self.total) > 0.01:  # Show tax if there's a difference
            tax = self.total - subtotal
            print(f"💸 Tax:          ${tax:>8.2f}")
        print(f"💰 Total Amount: ${self.total:>8.2f}")
        print("=" * 60)
        print("✨ Thank you for using ORBIT! ✨")
        print("=" * 60)


class DBItem(Base):
    __tablename__ = "items"
    item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"))
    name: Mapped[str] = mapped_column()
    price: Mapped[float] = mapped_column()

    # Define the relationship back to DBReceipt
    receipt: Mapped[DBReceipt] = relationship("DBReceipt", back_populates="items")

    def __repr__(self):
        return f"<DBItem(item_id={self.item_id}, name={self.name}, price={self.price})>"


if __name__ == "__main__":
    try:
        Session = sessionmaker(bind=engine)
        Base.metadata.create_all(engine)
        
        session = Session()
        
        # Clear existing records first
        clear_database(session)
        
        image_path = "receipt.png"
        print("🔍 Processing receipt image...")
        response = generate_response(image_path=image_path, response_format=Recipe)
        recipe_instance = response.choices[0].message.parsed

        new_receipt = DBReceipt(
            tag=recipe_instance.tag,
            total=recipe_instance.total,
        )
        session.add(new_receipt)
        for item in recipe_instance.items:
            new_item = DBItem(name=item.name, price=item.price, receipt=new_receipt)
            session.add(new_item)
        session.commit()

        # Print receipt:
        stmt = select(DBReceipt).order_by(DBReceipt.id)
        receipts = session.execute(stmt).scalars().all()

        print("\n" + "🎉" * 20)
        print("📊 RECEIPT PROCESSING COMPLETE!")
        print("🎉" * 20)
        
        for receipt in receipts:
            receipt.pretty_print()
        
        # # Print summary statistics
        # print("\n" + "-" * 20)
        # print("📊 DATABASE SUMMARY")
        # print("-" * 20)
        # print(f"📄 Total Receipts: {len(receipts)}")
        # total_items = sum(len(receipt.items) for receipt in receipts)
        # print(f"🛒 Total Items: {total_items}")
        # total_amount = sum(receipt.total for receipt in receipts)
        # print(f"💰 Total Value: ${total_amount:.2f}")
        # print("-" * 20)
            
    except FileNotFoundError:
        print("❌ Error: receipt.png file not found. Please ensure the image file exists in the current directory.")
    except Exception as e:
        print(f"❌ Error: {e}")
        print("🔑 Please check your OpenAI API key in the .env file.") 