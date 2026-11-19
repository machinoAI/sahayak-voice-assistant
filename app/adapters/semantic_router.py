"""
In-process, zero-external-dependency semantic router using sparse
prototype centroid embeddings (OATS, arXiv:2603.13426).
Executes on CPU in <0.5ms with deterministic routing behavior.
"""

import math
import re
import unicodedata
from typing import Dict, List, Set, Tuple
from app.interfaces.adapters import QueryIntent, SemanticRouterProtocol

class SemanticRouterAdapter(SemanticRouterProtocol):
    """
    Evaluates incoming user utterances against pre-computed centroid vectors
    representing distinct routing intents:
    - LOCAL_SCHEME_FAQ: Domestic welfare schemes, citizen documentation, and assistant FAQs.
    - REALTIME_TEMPORAL: Breaking news, live scores, current weather, dynamic prices.
    - OUT_OF_DOMAIN: General trivia, world history, science, open-domain questions.
    """

    DEFAULT_TEMPORAL_SEED: List[str] = [
        "what is the latest news in india today",
        "current weather forecast in new delhi",
        "live cricket score match update",
        "what is today gold and silver price",
        "latest stock price of tata motors",
        "what happened in parliament yesterday",
        "is it raining right now in bangalore",
        "breaking news headlines tonight",
        "current petrol diesel price update",
        "election voting results live update",
        "weather temperature today",
        "latest updates now",
        # Devanagari Hindi temporal exemplars
        "आज का ताजा समाचार क्या है",
        "दिल्ली में आज का मौसम कैसा है",
        "लाइव क्रिकेट स्कोर अपडेट",
        "आज सोने और चांदी का भाव क्या है",
        "पेट्रोल और डीजल का आज का दाम",
        "आज की बड़ी खबरें",
        "कल क्या हुआ था समाचार",
        # Hinglish temporal exemplars
        "aaj ka taaza samachar kya hai",
        "aaj delhi ka mausam kaisa hai",
        "live cricket match score kya hai",
        "petrol diesel ka aaj ka rate",
        "aaj ki latest khabar batao",
    ]

    DEFAULT_LOCAL_SCHEME_SEED: List[str] = [
        "how to apply for pm kisan scheme",
        "eligibility criteria for ayushman bharat card",
        "documents required for ration card application",
        "government pension scheme for senior citizens",
        "pradhan mantri awas yojana subsidy status",
        "farmer fertilizer subsidy registration portal",
        "how can i get an e shram card",
        "sukanya samriddhi yojana interest rate and benefits",
        "what is sahayak and what services does it provide",
        "government welfare benefits for rural farmers",
        "how to download aadhar card online",
        "schemes for pregnant women and children",
        # Devanagari Hindi local scheme exemplars
        "पीएम किसान योजना के लिए आवेदन कैसे करें",
        "आयुष्मान भारत कार्ड की पात्रता क्या है",
        "राशन कार्ड बनवाने के लिए कौन से दस्तावेज चाहिए",
        "वरिष्ठ नागरिकों के लिए सरकारी पेंशन योजना",
        "प्रधानमंत्री आवास योजना की सब्सिडी और स्थिति",
        "ई श्रम कार्ड कैसे बनाएं",
        "सुकन्या समृद्धि योजना के लाभ और नियम",
        "सहायक क्या है और यह क्या मदद करता है",
        "आधार कार्ड ऑनलाइन कैसे डाउनलोड करें",
        "महिलाओं और बच्चों के लिए सरकारी योजनाएं",
        # Hinglish local scheme exemplars
        "pm kisan yojana me aavedan kaise kare",
        "ayushman card ki patrata kya hai",
        "ration card ke liye kya documents chahiye",
        "pradhan mantri awas yojana subsidy status",
        "sahayak kya hai aur kaise kaam karta hai",
        "aadhar card download kaise kare",
    ]

    DEFAULT_OUT_OF_DOMAIN_SEED: List[str] = [
        "who invented the first telephone",
        "what is the capital of madagascar",
        "explain quantum computing in simple terms",
        "who was the first president of the united states",
        "how do airplanes fly physics",
        "recipe for chocolate chip cookies",
        "distance between earth and moon",
        "write a python function to sort a list",
        "history of the french revolution",
        "who wrote the play romeo and juliet",
        # Hindi & Hinglish out-of-domain exemplars
        "पृथ्वी और चंद्रमा के बीच की दूरी कितनी है",
        "टेलीफोन का आविष्कार किसने किया था",
        "कंप्यूटर कैसे काम करता है समझाइए",
        "roti kaise banate hain recipe",
        "duniya ka sabse bada janwar kaun sa hai",
    ]

    STOP_WORDS: Set[str] = {
        "का", "के", "की", "और", "है", "हैं", "में", "से", "को", "पर", "था", "थी", "थे", "क्या",
        "the", "is", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for", "it", "what",
    }

    def __init__(
        self,
        temporal_threshold: float = 0.12,
        local_threshold: float = 0.12,
    ) -> None:
        self.temporal_threshold = temporal_threshold
        self.local_threshold = local_threshold
        self._centroids: Dict[QueryIntent, Dict[str, float]] = {}
        self._build_centroids()

    def _extract_features(self, text: str) -> Dict[str, float]:
        """Extracts word unigrams and character 3-grams with L2 normalization."""
        features: Dict[str, float] = {}
        normalized = unicodedata.normalize("NFKC", text or "")
        cleaned = re.sub(r"[^\w\s]", " ", normalized.lower())
        words = cleaned.split()

        # Word unigrams
        for w in words:
            if w in self.STOP_WORDS:
                continue
            if len(w) > 1:
                features[f"w:{w}"] = features.get(f"w:{w}", 0.0) + 1.0

        # Character 3-grams (for inflection & typo resilience)
        for w in words:
            if w in self.STOP_WORDS:
                continue
            if len(w) >= 3:
                padded = f"_{w}_"
                for i in range(len(padded) - 2):
                    ngram = padded[i : i + 3]
                    features[f"c:{ngram}"] = features.get(f"c:{ngram}", 0.0) + 0.5

        # L2 Unit Normalization
        norm = math.sqrt(sum(v * v for v in features.values())) or 1.0
        return {k: v / norm for k, v in features.items()}

    def _build_centroids(self) -> None:
        """Computes normalized centroid vectors for each class from seed exemplars."""
        clusters = {
            QueryIntent.REALTIME_TEMPORAL: self.DEFAULT_TEMPORAL_SEED,
            QueryIntent.LOCAL_SCHEME_FAQ: self.DEFAULT_LOCAL_SCHEME_SEED,
            QueryIntent.OUT_OF_DOMAIN: self.DEFAULT_OUT_OF_DOMAIN_SEED,
        }

        for intent, seeds in clusters.items():
            centroid: Dict[str, float] = {}
            for text in seeds:
                vec = self._extract_features(text)
                for k, v in vec.items():
                    centroid[k] = centroid.get(k, 0.0) + v

            # Normalize centroid
            norm = math.sqrt(sum(v * v for v in centroid.values())) or 1.0
            self._centroids[intent] = {k: v / norm for k, v in centroid.items()}

    def _cosine_similarity(self, v1: Dict[str, float], v2: Dict[str, float]) -> float:
        """Computes sparse inner product since vectors are pre-normalized to unit norm."""
        intersection = set(v1.keys()) & set(v2.keys())
        return sum(v1[k] * v2[k] for k in intersection)

    def classify_intent(self, query: str) -> QueryIntent:
        """
        Classifies input query intent into pre-defined routing categories in <0.5ms.
        """
        if not query or not query.strip():
            return QueryIntent.OUT_OF_DOMAIN

        q_vec = self._extract_features(query)

        sim_temporal = self._cosine_similarity(
            q_vec, self._centroids[QueryIntent.REALTIME_TEMPORAL]
        )
        sim_local = self._cosine_similarity(
            q_vec, self._centroids[QueryIntent.LOCAL_SCHEME_FAQ]
        )
        sim_ood = self._cosine_similarity(
            q_vec, self._centroids[QueryIntent.OUT_OF_DOMAIN]
        )

        # Prioritize temporal real-time triggers to protect fresh fact retrieval
        if sim_temporal >= self.temporal_threshold and sim_temporal >= sim_local:
            return QueryIntent.REALTIME_TEMPORAL

        # Local domain check
        if sim_local >= self.local_threshold and sim_local >= sim_ood:
            return QueryIntent.LOCAL_SCHEME_FAQ

        if sim_temporal >= self.temporal_threshold:
            return QueryIntent.REALTIME_TEMPORAL

        return QueryIntent.OUT_OF_DOMAIN
