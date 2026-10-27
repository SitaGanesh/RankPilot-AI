"""Marketing Intelligence Agent — LangChain chains.

Uses Groq (same LLM as the rest of the project) with structured output
forced via Pydantic models to guarantee every field is present.
"""
from __future__ import annotations

import os

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

from . import prompts
from .schemas import PageReport, ResearchBrief, SiteSynthesis


def get_llm(temperature: float = 0) -> ChatGroq:
    return ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        temperature=temperature,
        api_key=os.getenv("GROQ_API_KEY", ""),
    )


def brief_chain():
    """Convert raw research dossier text → structured ResearchBrief."""
    llm = get_llm(0)
    parser = PydanticOutputParser(pydantic_object=ResearchBrief)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Extract a structured ResearchBrief from this research dossier.\n{format_instructions}"),
        ("human", "{dossier}"),
    ]).partial(format_instructions=parser.get_format_instructions())
    return prompt | llm | parser


def page_chain():
    """Audit a single page → structured PageReport."""
    llm = get_llm(0)
    parser = PydanticOutputParser(pydantic_object=PageReport)
    prompt = ChatPromptTemplate.from_messages([
        ("system", prompts.PAGE_SYSTEM + "\n{format_instructions}"),
        ("human", prompts.PAGE_HUMAN),
    ]).partial(format_instructions=parser.get_format_instructions())
    return prompt | llm | parser


def site_chain():
    """Synthesise page reports into SiteSynthesis."""
    llm = get_llm(0)
    parser = PydanticOutputParser(pydantic_object=SiteSynthesis)
    prompt = ChatPromptTemplate.from_messages([
        ("system", prompts.SITE_SYSTEM + "\n{format_instructions}"),
        ("human", prompts.SITE_HUMAN),
    ]).partial(format_instructions=parser.get_format_instructions())
    return prompt | llm | parser
