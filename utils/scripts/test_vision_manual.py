#!/usr/bin/env python3
"""
Quick manual test for vision processing with Gemini
"""
import asyncio
import httpx
from PIL import Image, ImageDraw
import io
import time

SERVER_URL = "http://localhost:3000"
API_KEY = "files"

async def test_vision():
    print("🎨 Creating test image...")

    # Create a simple test image
    img = Image.new('RGB', (400, 300), color='lightblue')
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "TEST IMAGE", fill='black')
    draw.text((20, 50), "Vision API Test", fill='darkblue')
    draw.rectangle([20, 100, 150, 200], outline='red', width=3)
    draw.text((160, 140), "Red Box", fill='red')

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    png_content = buffer.getvalue()

    print(f"✅ Created PNG image ({len(png_content)} bytes)")

    async with httpx.AsyncClient(timeout=180.0) as client:
        # Upload
        print("\n📤 Uploading image...")
        files = {"file": ("test_vision.png", png_content, "image/png")}
        headers = {"X-API-Key": API_KEY}

        response = await client.post(
            f"{SERVER_URL}/api/files/upload",
            headers=headers,
            files=files
        )

        if response.status_code != 200:
            print(f"❌ Upload failed: {response.status_code} - {response.text}")
            return

        data = response.json()
        file_id = data["file_id"]
        print(f"✅ Uploaded: {file_id}")
        print(f"   Status: {data['status']}")

        # Poll for completion
        print("\n⏳ Waiting for vision processing...")
        print("   (Check logs/orbit.log for detailed progress)")

        for i in range(150):  # 150 seconds max
            await asyncio.sleep(1)

            response = await client.get(
                f"{SERVER_URL}/api/files/{file_id}",
                headers=headers
            )

            if response.status_code == 200:
                file_info = response.json()
                status = file_info.get('processing_status', 'unknown')
                chunks = file_info.get('chunk_count', 0)

                if i % 10 == 0:  # Print every 10 seconds
                    print(f"   [{i}s] Status: {status}, Chunks: {chunks}")

                if status == 'completed':
                    print(f"\n✅ Processing completed!")
                    print(f"   Chunks created: {chunks}")
                    if chunks > 0:
                        print("\n🎉 VISION PROCESSING WORKS!")
                    else:
                        print("\n⚠️  Completed but no chunks - check error_message")
                        if file_info.get('error_message'):
                            print(f"   Error: {file_info['error_message']}")

                    # Cleanup
                    await client.delete(f"{SERVER_URL}/api/files/{file_id}", headers=headers)
                    return

                elif status == 'failed':
                    print(f"\n❌ Processing failed!")
                    if file_info.get('error_message'):
                        print(f"   Error: {file_info['error_message']}")

                    # Cleanup
                    await client.delete(f"{SERVER_URL}/api/files/{file_id}", headers=headers)
                    return

        print(f"\n⏱️  Timeout after 150 seconds")
        print("   Check logs/orbit.log for details")

        # Cleanup
        try:
            await client.delete(f"{SERVER_URL}/api/files/{file_id}", headers=headers)
        except:
            pass

if __name__ == "__main__":
    print("=" * 60)
    print("Vision Processing Test - Gemini")
    print("=" * 60)
    asyncio.run(test_vision())
