from ollama import chat
from ddgs import DDGS
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import json
import textwrap

def search_web(query):

    try:
        results = []

        with DDGS() as ddgs:
            for r in ddgs.text(query,max_results=5):
                results.append({"title": r["title"],"url": r["href"]})

        return results

    except Exception as e:
        return {"error": str(e)}

def visit_page(url):

    try:

        headers = {"User-Agent":"Mozilla/5.0"}
        response = requests.get(url,headers=headers,timeout=10)
        soup = BeautifulSoup(response.text,"html.parser")
        text = soup.get_text(separator=" ",strip=True)
        return text[:2500]

    except Exception as e:
        return f"ERROR: {e}"
    
def browser_visit(url):

    try:

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url,wait_until="domcontentloaded",timeout=15000)
            page_text = page.inner_text("body")
            browser.close()
            return page_text[:3000]

    except Exception as e:
        return f"ERROR: {e}"


tools = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description":
            "Search internet for products, stores and information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "visit_page",
            "description":
            "Visit a webpage and extract readable text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_visit",
            "description":
            "Open a webpage in a real browser. "
            "Use when visit_page cannot access "
            "or extract sufficient information "
            "from a webpage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string"
                    }
                },
                "required": ["url"]
            }
        }
    }
]

visited_urls = set()
useful_urls = set()
failed_urls = set()
searched_queries = set()

SYSTEM_PROMPT = """
You are a research agent.

Your goal is to investigate questions, gather evidence from multiple sources,
analyze information, and provide evidence-based conclusions.

Core Principles

- Search results are navigation aids, not evidence.
- Never make claims without supporting evidence.
- Never invent facts, prices, ratings, statistics, dates, reviews, or quotations.
- If information cannot be verified, explicitly state that it could not be verified.
- Prefer evidence over assumptions.

Research Process

1. Search for relevant information.
2. Evaluate available sources.
3. Select promising websites.
4. Gather evidence.
5. Compare and analyze findings.
6. Produce a conclusion supported by evidence.

Evidence Requirements

A conclusion is only valid when:

- Evidence has been gathered from multiple useful sources.
- Information has been compared and analyzed.
- Claims are supported by gathered evidence.

Useful Source Criteria

A useful source contains relevant factual information related to the research question.

Failed Source Criteria

A failed source includes:

- Access denied pages
- Captcha pages
- Cloudflare pages
- Error pages
- 404 pages
- Pages without useful information

Website Selection Rules

- Do not simply visit the first search result.
- Evaluate multiple search results.
- Prefer authoritative and relevant sources.
- Prefer unexplored sources.
- Avoid revisiting failed sources.
- Avoid revisiting already inspected sources unless necessary.

Reasoning
Before every action:

- Explain what information is missing.
- Explain why the chosen tool is appropriate.
- Explain what evidence you hope to gather.

Stopping Rules

- Do not stop after finding information from a single source.
- Continue gathering evidence if conclusions cannot yet be supported.
- Verify conclusions before answering.

Research Completion Criteria

Research is complete when:

- At least 3 useful sources have been inspected.
- Major claims are supported by evidence.
- No major information gaps remain.

When research is complete:

- Stop researching.
- Produce the final answer.
- Do not continue searching unnecessarily.
"""


messages = [{
        "role": "system",
        "content": SYSTEM_PROMPT
    }]

query = input("\nWhat would you like to search for?\n> ")

messages.append({
    "role": "user",
    "content": query
})

MAX_STEPS = 12
MIN_SOURCES = 3

for step in range(MAX_STEPS):
    print("\n" + "=" * 60)
    print(f"AGENT STEP {step + 1}")
    print("=" * 60)

    extra_instruction = ""

    if step >= MAX_STEPS - 3:
        extra_instruction = """
    Research should conclude soon.

    Prioritize synthesis and analysis.

    Only perform additional searches if
    critical information is missing.
    """

    state_message = {
        "role": "system",
        "content":
        f"""
Current research state
Current step: {step + 1} 
Maximum steps: {MAX_STEPS}
Searches performed:
{list(searched_queries)}

Visited URLs:
{list(visited_urls)}

Useful URLs:
{list(useful_urls)}

Failed URLs:
{list(failed_urls)}

Useful Source Count:
{len(useful_urls)}

Required Sources:
{MIN_SOURCES}

Rules:
- Never repeat an identical search query.
- If a search was unsuccessful, reformulate it.
- Avoid revisiting URLs.
- Avoid revisiting failed URLs.
- Prefer unexplored websites.
{extra_instruction} 
"""}

    current_messages = (messages + [state_message])
    response = chat(model="qwen2.5:7b",messages=current_messages,tools=tools)
    message = response["message"]

    if message.get("content"):
        print("\n CURRENT ANALYSIS: ")
        print("-" * 40)
        print(message["content"])

    if message.get("tool_calls"):
        messages.append(message)
        for tool_call in message["tool_calls"]:
            name = tool_call["function"]["name"]
            args = tool_call["function"]["arguments"]

            print(f"\nTOOL CALLED: {name}")
            print(f"ARGS: {args}")

            if name == "search_web":
                query_text = (args["query"].lower().strip())

                if query_text in searched_queries:
                    print("\nDUPLICATE SEARCH BLOCKED")
                    result = {"error":f"Search '{query_text}' was already performed. Choose a different query"}

                else:
                    searched_queries.add(query_text)
                    result = search_web(**args)

                print("\nSEARCH RESULTS:")

                if isinstance(result, dict) and "error" in result:
                    print("\nSEARCH FAILED:")
                    print(result["error"])

                else:
                    for i, item in enumerate(result,start=1):
                        print(
                            f"{i}. "
                            f"{item['title']}\n"
                            f"   {item['url']}\n"
                        )

            elif name == "visit_page":
                already_seen = (args["url"] in visited_urls)
                if already_seen:
                    print("\nDUPLICATE URL BLOCKED")
                    result = f"URL {args['url']} has been already visited."
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(result)
                    })
                    continue

                else:
                    visited_urls.add(args["url"])
                    result = visit_page(**args)

                page_text = (result.lower())

                bad_signals = [
                    "access denied",
                    "404",
                    "not found",
                    "cloudflare",
                    "enable cookies",
                    "blocked",
                    "captcha"]
                
                if len(result) > 300 and not any(signal in page_text for signal in bad_signals):
                    useful_urls.add(args["url"])
                    failed_urls.discard(args["url"])

                else:
                    failed_urls.add(args["url"])

                if not already_seen:
                    print("\nVISITED:")
                    print(args["url"])
                    print("\nPAGE PREVIEW:")
                    print(textwrap.shorten(result,width=500,placeholder="..."))

            elif name == "browser_visit":
                already_seen = (args["url"] in visited_urls)
                if already_seen:
                    print("\nDUPLICATE URL BLOCKED")
                    result = f"URL {args['url']} has been already visited."
                    messages.append({
                        "role": "tool",
                        "content": json.dumps(result)
                    })
                    continue

                else:
                    visited_urls.add(args["url"])
                    result = browser_visit(**args)

                page_text = result.lower()

                bad_signals = [
                    "access denied",
                    "404",
                    "not found",
                    "cloudflare",
                    "enable cookies",
                    "blocked",
                    "captcha"]

                if len(result) > 300 and not any(signal in page_text for signal in bad_signals):
                    useful_urls.add(args["url"])
                    failed_urls.discard(args["url"])

                else:
                    failed_urls.add(args["url"])

                if not already_seen:
                    print("\nBROWSER VISITED:")
                    print(args["url"])
                    print("\nPAGE PREVIEW:")
                    print(textwrap.shorten(result,width=500,placeholder="..."))

            else:
                result = "Unknown tool"

            messages.append({"role": "tool","content":json.dumps(result)})

    else:
        content = (message.get("content","").lower())

        unfinished_signals = [
        "research not finished",
        "continue researching",
        "more research",
        "more evidence",
        "need more evidence",
        "need more information",
        "need additional information",
        "next source",
        "another source",
        "let's search",
        "let's visit",
        "let's gather",
        "let's continue",
        "i will visit",
        "i will search"]

        if any(
            signal in content
            for signal in unfinished_signals
        ):

            print("\nRESEARCH NOT FINISHED")

            messages.append({
                "role": "user",
                "content":
                """
                You indicated that more
                research is required.
                Continue researching.
                Do not provide a final
                answer yet.
                """
            })

            continue
        if step >= MAX_STEPS - 2 and len(useful_urls) >= MIN_SOURCES:
            print("\nFORCING FINAL SYNTHESIS")

            messages.append({
                "role": "user",
                "content":
                """
                Research appears sufficient.

                Produce the final answer.

                Do not continue searching.
                Summarize evidence gathered.
                """
            })

            continue
        if len(useful_urls) < MIN_SOURCES:
            print("\nGUARDRAIL TRIGGERED")
            print(
                f"Only "
                f"{len(useful_urls)} "
                f"useful website(s)."
            )

            messages.append({
                "role": "user",
                "content":
                f"""
You have inspected only
{len(useful_urls)} of {MIN_SOURCES} required sources.
A recommendation is not valid yet.
Requirements:
- Inspect at least 3 useful websites.
- Compare information from multiple sources.
- Gather additional evidence.
Continue researching.
"""
})
            continue

        print("\n" + "=" * 60)
        print("FINAL RECOMMENDATION")
        print("=" * 60)

        print(message["content"])

        print("\n" + "=" * 60)
        print("VISITED URLS")
        print("=" * 60)

        for url in visited_urls:
            print(url)

        print("\n" + "=" * 60)
        print("USEFUL URLS")
        print("=" * 60)

        for url in useful_urls:
            print(url)

        print("\n" + "=" * 60)
        print("FAILED URLS")
        print("=" * 60)

        for url in failed_urls:
            print(url)
        break

else:
    print("\nReached maximum steps.")