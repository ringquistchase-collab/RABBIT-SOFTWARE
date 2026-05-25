"""
Prompt templates for RabbitOS AI tasks.
"""

ANALYZE_TEMPLATE = """\
You are RabbitOS AI. Analyze the following data and provide a concise structured report.

Data:
{content}

Context:
{context}

Respond with: findings, anomalies (if any), and recommended actions.
"""

CODE_REVIEW_TEMPLATE = """\
You are a senior RabbitOS engineer. Review the following code for bugs, security issues, and style.

Code:
{content}

Provide: summary, issues found (severity: low/medium/high), and suggested fixes.
"""

RESEARCH_TEMPLATE = """\
You are a RabbitOS research assistant. Answer the following question thoroughly and accurately.

Question: {content}

Context: {context}
"""

SECURITY_TEMPLATE = """\
You are a RabbitOS security auditor. Evaluate the following event for security risks.

Event:
{content}

Return: risk level (low/medium/high/critical), reason, and recommended action.
"""


def format_prompt(template: str, **kwargs) -> str:
    return template.format(**kwargs)
