#!/usr/bin/env python3
"""
Manual test script for vision processing with AI services.

Usage:
    python test_vision_manual.py <file_path> [options]

Arguments:
    file_path      Path to the image file to upload and test

Options:
    --server-url   Server URL (default: http://localhost:3000)
    --api-key      API key for authentication (default: 'files')
    --timeout      Maximum wait time in seconds (default: 150)

Required:
    --prompt       Custom prompt for vision analysis

Examples:
    # Test with a local image file
    python test_vision_manual.py /path/to/image.png --prompt "Describe this image in detail"

    # Test with a custom prompt and different server
    python test_vision_manual.py ./test_image.jpg --prompt "What colors are in this image?" --server-url http://localhost:3000

    # Test with custom timeout and prompt
    python test_vision_manual.py image.png --prompt "Describe the main objects" --timeout 300

Note:
    - The AI service provider is configured in config/vision.yaml (vision.provider setting)
    - Supported image formats: PNG, JPEG, GIF, BMP, TIFF, WebP
    - The script will upload the file, wait for processing, and display the vision response
    - The prompt will be used for vision analysis instead of default prompts
    - The file will be automatically deleted after testing
"""
import asyncio
import httpx
import argparse
import os
import mimetypes
from pathlib import Path

SERVER_URL = "http://localhost:3000"
API_KEY = "files"
DEFAULT_TIMEOUT = 150

async def test_vision(file_path: str, server_url: str, api_key: str, timeout: int, prompt: str):
    """Test vision processing with the specified image file."""
    # Validate file exists
    if not os.path.exists(file_path):
        print(f"❌ Error: File not found: {file_path}")
        return
    
    # Read file
    print(f"📁 Reading image file: {file_path}")
    try:
        with open(file_path, 'rb') as f:
            file_content = f.read()
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return
    
    # Determine MIME type
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type or not mime_type.startswith('image/'):
        # Try to infer from extension
        ext = Path(file_path).suffix.lower()
        mime_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
            '.webp': 'image/webp'
        }
        mime_type = mime_map.get(ext, 'image/png')
    
    filename = os.path.basename(file_path)
    print(f"✅ Loaded image: {filename} ({len(file_content)} bytes, {mime_type})")
    print(f"🌐 Server URL: {server_url}")
    print(f"📝 Using prompt: {prompt}")
    print("ℹ️  Vision provider is configured in config/vision.yaml")

    file_id = None
    async with httpx.AsyncClient(timeout=180.0) as client:
        # Upload
        print("\n📤 Uploading image...")
        files = {"file": (filename, file_content, mime_type)}
        # Pass prompt as form data
        data = {"prompt": prompt}
        headers = {"X-API-Key": api_key}

        response = await client.post(
            f"{server_url}/api/files/upload",
            headers=headers,
            files=files,
            data=data
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

        for i in range(timeout):
            await asyncio.sleep(1)

            response = await client.get(
                f"{server_url}/api/files/{file_id}",
                headers=headers
            )

            if response.status_code == 200:
                file_info = response.json()
                status = file_info.get('processing_status', 'unknown')
                chunks = file_info.get('chunk_count', 0)

                if i % 10 == 0:  # Print every 10 seconds
                    print(f"   [{i}s] Status: {status}, Chunks: {chunks}")

                if status == 'completed':
                    print("\n✅ Processing completed!")
                    print(f"   Chunks created: {chunks}")
                    if chunks > 0:
                        print("\n🎉 VISION PROCESSING WORKS!")
                        
                        # Retrieve and display vision response
                        print("\n📊 Retrieving vision provider response...")
                        try:
                            # Query the file to get chunks (use a generic query to get all chunks)
                            query_headers = dict(headers)
                            query_headers["Content-Type"] = "application/json"
                            query_response = await client.post(
                                f"{server_url}/api/files/{file_id}/query",
                                headers=query_headers,
                                json={"query": "image content", "max_results": chunks}
                            )
                            
                            if query_response.status_code == 200:
                                query_data = query_response.json()
                                results = query_data.get('results', [])
                                
                                if results:
                                    print("\n" + "=" * 60)
                                    print("VISION PROVIDER RESPONSE")
                                    print("=" * 60)
                                    
                                    # Extract and display only the LLM response (image description)
                                    # The content format is: "Image Description:\n{description}\n\nExtracted Text:\n{text}"
                                    vision_responses = []
                                    for result in results:
                                        content = result.get('content', '')
                                        if content:
                                            # Parse to extract just the image description (LLM response)
                                            if "Image Description:" in content and "Extracted Text:" in content:
                                                # Extract everything between "Image Description:" and "Extracted Text:"
                                                start_idx = content.find("Image Description:") + len("Image Description:")
                                                end_idx = content.find("Extracted Text:")
                                                if start_idx < end_idx:
                                                    description = content[start_idx:end_idx].strip()
                                                    if description:
                                                        vision_responses.append(description)
                                            elif "Image Description:" in content:
                                                # If only description is present
                                                start_idx = content.find("Image Description:") + len("Image Description:")
                                                description = content[start_idx:].strip()
                                                if description:
                                                    vision_responses.append(description)
                                            else:
                                                # If format is different, show the content as-is
                                                vision_responses.append(content.strip())
                                    
                                    # Display the vision response(s) - just the LLM response, no chunk formatting
                                    if vision_responses:
                                        # Combine all responses (usually just one)
                                        full_response = "\n\n".join(vision_responses)
                                        print(f"\n{full_response}")
                                    else:
                                        # Fallback: show first chunk content if parsing fails
                                        print(f"\n{results[0].get('content', 'No content available')}")
                                    
                                    print("\n" + "=" * 60)
                                else:
                                    print("⚠️  No content returned from query")
                            else:
                                print(f"⚠️  Could not retrieve chunks: {query_response.status_code}")
                                print(f"   Response: {query_response.text}")
                        except Exception as e:
                            print(f"⚠️  Error retrieving vision response: {e}")
                    else:
                        print("\n⚠️  Completed but no chunks - check error_message")
                        if file_info.get('error_message'):
                            print(f"   Error: {file_info['error_message']}")

                    # Cleanup
                    try:
                        await client.delete(f"{server_url}/api/files/{file_id}", headers=headers)
                    except Exception:
                        pass
                    return

                elif status == 'failed':
                    print("\n❌ Processing failed!")
                    if file_info.get('error_message'):
                        print(f"   Error: {file_info['error_message']}")

                    # Cleanup
                    try:
                        await client.delete(f"{server_url}/api/files/{file_id}", headers=headers)
                    except Exception:
                        pass
                    return

        print(f"\n⏱️  Timeout after {timeout} seconds")
        print("   Check logs/orbit.log for details")

        # Cleanup on timeout
        if file_id:
            try:
                await client.delete(f"{server_url}/api/files/{file_id}", headers=headers)
            except Exception:
                pass

def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description='Test vision processing with AI services',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_vision_manual.py /path/to/image.png --prompt "Describe this image"
  python test_vision_manual.py ./test_image.jpg --prompt "What colors are in this image?" --server-url http://localhost:3000
  python test_vision_manual.py image.png --prompt "Describe the main objects" --timeout 300
        """
    )
    
    parser.add_argument(
        'file_path',
        type=str,
        help='Path to the image file to upload and test'
    )
    
    parser.add_argument(
        '--server-url',
        type=str,
        default=SERVER_URL,
        help=f'Server URL (default: {SERVER_URL})'
    )
    
    parser.add_argument(
        '--api-key',
        type=str,
        default=API_KEY,
        help=f'API key for authentication (default: {API_KEY})'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f'Maximum wait time in seconds (default: {DEFAULT_TIMEOUT})'
    )
    
    parser.add_argument(
        '--prompt',
        type=str,
        required=True,
        help='Custom prompt for vision analysis (required)'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Vision Processing Test")
    print("=" * 60)
    
    asyncio.run(test_vision(
        file_path=args.file_path,
        server_url=args.server_url,
        api_key=args.api_key,
        timeout=args.timeout,
        prompt=args.prompt
    ))

if __name__ == "__main__":
    main()
