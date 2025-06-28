from .default_prompt import default_prompt
from .executive_summary import executive_summary_prompt
from .market_analysis import market_analysis_prompt
from .marketing_strategy import marketing_stratgy_prompt
from .financial_projection import financial_projection_prompt
from .implementation_timeline import implementation_timeline_prompt


chat_type_prompts ={
    "executive_summary": executive_summary_prompt,
    "market_analysis":market_analysis_prompt,
    "marketing_strategy":marketing_stratgy_prompt,
    "financial_projection": financial_projection_prompt,
    "implementation_timeline":implementation_timeline_prompt,
}

def get_prompt(chat_type:str)-> str:
    return chat_type_prompts.get(chat_type,default_prompt)