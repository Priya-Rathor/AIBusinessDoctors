from langchain_community.tools.tavily_search import TavilySearchResults


search_tool = TavilySearchResults(max_results=4)
tools = [search_tool]