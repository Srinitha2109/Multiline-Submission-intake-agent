import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.trace import Status, StatusCode

# If installed, this automatically traces Gemini calls
try:
    from openinference.instrumentation.gemini import GeminiInstrumentor
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False

try:
    from openinference.instrumentation.vertexai import VertexAIInstrumentor
    HAS_VERTEX = True
except ImportError:
    HAS_VERTEX = False

try:
    from openinference.instrumentation.litellm import LiteLLMInstrumentor
    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False

try:
    from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
    HAS_GOOGLE_GENAI = True
except ImportError:
    HAS_GOOGLE_GENAI = False


class ArizeProjectInjector(SpanProcessor):
    """Automatically injects Arize project attributes into every span."""
    def on_start(self, span, parent_context=None):
        if span.is_recording():
            span.set_attribute("arize.project.name", "multiline-intake-agent")
            span.set_attribute("model_id", "multiline-intake-agent")
            span.set_attribute("queue", "annotation_review")


def setup_arize():
    """Set up OpenTelemetry tracing and export to Arize AI."""
    space_key = os.environ.get("ARIZE_SPACE_ID")
    api_key = os.environ.get("ARIZE_API_KEY")
    
    if not space_key or not api_key:
        print("Warning: Arize credentials missing in .env. Tracing will run locally only.")
        return

    # ADK already initializes a TracerProvider! We cannot override it.
    # Instead, we just get the existing one.
    tracer_provider = trace.get_tracer_provider()
    
    # If we are running a raw script and no provider has been set yet,
    # trace.get_tracer_provider() returns a ProxyTracerProvider which lacks add_span_processor.
    if not hasattr(tracer_provider, "add_span_processor"):
        tracer_provider = TracerProvider()
        trace.set_tracer_provider(tracer_provider)
    
    endpoint = "https://otlp.arize.com/v1"
    headers = {
        "space_id": space_key,
        "Authorization": f"Bearer {api_key}"
    }
    exporter = OTLPSpanExporter(endpoint=f"{endpoint}/traces", headers=headers)
    
    # Add our attribute injector FIRST, then the Arize exporter
    tracer_provider.add_span_processor(ArizeProjectInjector())
    tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
    
    if HAS_GEMINI:
        GeminiInstrumentor().instrument()
        print("Gemini instrumentation attached.")
    
    if HAS_VERTEX:
        VertexAIInstrumentor().instrument()
        print("Vertex AI instrumentation attached.")
        
    if HAS_LITELLM:
        LiteLLMInstrumentor().instrument()
        print("LiteLLM instrumentation attached.")
        
    if HAS_GOOGLE_GENAI:
        GoogleGenAIInstrumentor().instrument()
        print("Google GenAI instrumentation attached.")
    
    print("Arize OTel tracing and instrumentation attached successfully.")


def get_tracer(name="multiline-intake-agent"):
    """Get the tracer for custom spans."""
    return trace.get_tracer(name)

# Automatically initialize tracing when this module is imported
setup_arize()
