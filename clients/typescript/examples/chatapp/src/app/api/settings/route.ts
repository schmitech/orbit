import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest): Promise<NextResponse> {
  const tokenLimit = process.env.VLLM_TOKEN_LIMIT
    ? parseInt(process.env.VLLM_TOKEN_LIMIT)
    : 4096;

  return NextResponse.json(
    {
      tokenLimit: tokenLimit,
    },
    { status: 200 }
  );
}
