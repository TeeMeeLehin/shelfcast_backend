import logging
import os
from openai import OpenAI
# Try anthropic if available, otherwise fallback to OpenAI for MVP
try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

logger = logging.getLogger(__name__)

class NarratorEngine:
    """
    Generates human-readable, analyst-style narratives for SKUs and Manager Digests.
    """
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        # Anthropic is optional
        self.anthropic_client = None
        if HAS_ANTHROPIC and os.getenv("ANTHROPIC_API_KEY"):
            try:
                self.anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            except Exception:
                logger.warning("Anthropic client initialization failed.")

    def generate_sku_narrative(self, tenant_id: str, sku_id: str, sku_name: str) -> str:
        """
        Generates a 2-3 sentence insight explaining the SKU's score.
        Uses context_builder for tenant-isolated data access.
        """
        from ai.context_builder import build_sku_context
        
        # Get tenant-isolated context
        context = build_sku_context(tenant_id, sku_id)
        
        if "error" in context:
            logger.error(f"Failed to build context for SKU {sku_id}: {context['error']}")
            return "Unable to generate narrative due to data access error."
        
        composite_score = context.get("composite_score", 50)
        breakdown = context.get("score_breakdown", {})
        signals = context.get("matched_signals", [])
        
        # Extract top 3 highest impact signals to feed the LLM
        top_signals = sorted(signals, key=lambda x: x.get("impact_score", 0), reverse=True)[:3]
        signal_texts = [f"- {s.get('source')}: {s.get('raw_content')} (Sentiment: {s.get('sentiment_score')}, Impact: {s.get('impact_score')})" for s in top_signals]
        
        prompt = f"""
        You are an expert FMCG retail analyst in Ghana.
        Write a concise, 2-3 sentence briefing for the SKU '{sku_name}' (ID: {sku_id}).
        
        Current Composite Intelligence Score: {composite_score}/100
        External Market Score: {breakdown.get('external_signals_score')}/100
        Internal Sales Velocity Score: {breakdown.get('internal_sales_score')}/100
        
        Recent Market Signals Driving this:
        {chr(10).join(signal_texts) if signal_texts else "No significant recent market signals."}
        
        REQUIREMENTS:
        - Do not use fluff or generic AI phrases like "In summary" or "It is important to note".
        - Be highly specific and data-driven.
        - Mention Ghanaian context if relevant.
        - End with a single clear stocking or pricing recommendation.
        """

        try:
            # Try Anthropic first if configured
            if self.anthropic_client:
                try:
                    response = self.anthropic_client.messages.create(
                        model="claude-3-5-sonnet-20240620",
                        max_tokens=150,
                        system="You are a strict, data-driven retail analyst. No fluff.",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    return response.content[0].text.strip()
                except Exception as anth_err:
                    logger.warning(f"Anthropic narrative failed for {sku_id}, falling back to OpenAI: {anth_err}")

            # Fallback to OpenAI (or default if Anthropic not configured)
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a strict, data-driven retail analyst. No fluff."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150
            )
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Complete failure generating narrative for {sku_id}: {e}")
            return "Narrative generation failed due to API errors."

    def generate_manager_digest(self, tenant_id: str, top_skus_data: list, anomalies: list) -> dict:
        """
        Generates the structured JSON for the morning manager email digest.
        """
        prompt = f"""
        You are the Chief Intelligence Officer for a Ghanaian retail business.
        Write a morning brief based on the following data.
        
        Top Moving SKUs:
        {top_skus_data}
        
        Market Anomalies:
        {anomalies}
        
        Output valid JSON with the following keys:
        - "executive_summary": A 2-sentence overview of the market today.
        - "top_movers_analysis": Why the top SKUs are moving.
        - "market_anomalies": Explanation of the anomalies.
        - "strategic_advice": 2 bullet points on what the manager should do today (e.g. stocking, pricing).
        """
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a retail CIO. Output MUST be valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            import json
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Failed to generate manager digest: {e}")
            return {"error": "Failed to generate digest"}

narrator_engine = NarratorEngine()
