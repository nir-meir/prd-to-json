"""
PRD Data Models - Structured representation of parsed PRD documents.

These models represent the intermediate format between raw PRD text
and the final INSAIT JSON output.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
from enum import Enum
from datetime import datetime


class Channel(Enum):
    """Supported communication channels."""
    VOICE = "voice"
    TEXT = "text"  # chat/whatsapp
    BOTH = "both"

    @classmethod
    def from_string(cls, value: str) -> 'Channel':
        """Parse channel from string, handling common variations."""
        value_lower = value.lower().strip()
        if value_lower in ('voice', 'audio', 'phone', 'call'):
            return cls.VOICE
        elif value_lower in ('text', 'chat', 'whatsapp', 'sms', 'message'):
            return cls.TEXT
        elif value_lower in ('both', 'all', 'dual', 'text + audio', 'audio + text'):
            return cls.BOTH
        else:
            return cls.BOTH  # Default to both if unclear


class Complexity(Enum):
    """PRD complexity levels for strategy selection."""
    SIMPLE = "simple"           # 1-3 features, < 10 nodes
    MEDIUM = "medium"           # 4-10 features, 10-50 nodes
    COMPLEX = "complex"         # 10-20 features, 50-100 nodes
    ENTERPRISE = "enterprise"   # 20+ features, 100+ nodes


class VariableType(Enum):
    """Supported variable types."""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"

    @classmethod
    def from_string(cls, value: str) -> 'VariableType':
        """Parse variable type from string."""
        value_lower = value.lower().strip()
        mapping = {
            'string': cls.STRING,
            'str': cls.STRING,
            'text': cls.STRING,
            'number': cls.NUMBER,
            'int': cls.NUMBER,
            'integer': cls.NUMBER,
            'float': cls.NUMBER,
            'decimal': cls.NUMBER,
            'boolean': cls.BOOLEAN,
            'bool': cls.BOOLEAN,
            'object': cls.OBJECT,
            'dict': cls.OBJECT,
            'json': cls.OBJECT,
            'array': cls.ARRAY,
            'list': cls.ARRAY,
        }
        return mapping.get(value_lower, cls.STRING)


class VariableSource(Enum):
    """Where a variable gets its value from."""
    USER = "user"       # Set by user input or system-computed
    COLLECT = "collect" # Collected via Collect nodes
    TOOL = "tool"       # Populated from API/tool responses


class FlowStepType(Enum):
    """Types of flow steps in a feature."""
    COLLECT = "collect"
    API_CALL = "api_call"
    CONDITION = "condition"
    CONVERSATION = "conversation"
    TRANSFER = "transfer"
    SET_VARIABLE = "set_variable"
    END = "end"
    LOOP = "loop"
    WAIT = "wait"


class HTTPMethod(Enum):
    """HTTP methods for API endpoints."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


@dataclass
class ValidationRule:
    """Validation rule for a variable or field."""
    type: str  # pattern, length, range, enum, custom
    params: Dict[str, Any] = field(default_factory=dict)
    message: str = ""

    @classmethod
    def pattern(cls, pattern: str, message: str = "") -> 'ValidationRule':
        return cls(type="pattern", params={"pattern": pattern}, message=message)

    @classmethod
    def length(cls, min_len: Optional[int] = None, max_len: Optional[int] = None, message: str = "") -> 'ValidationRule':
        return cls(type="length", params={"min": min_len, "max": max_len}, message=message)

    @classmethod
    def range(cls, min_val: Optional[float] = None, max_val: Optional[float] = None, message: str = "") -> 'ValidationRule':
        return cls(type="range", params={"min": min_val, "max": max_val}, message=message)

    @classmethod
    def enum(cls, options: List[str], message: str = "") -> 'ValidationRule':
        return cls(type="enum", params={"options": options}, message=message)


@dataclass
class Variable:
    """
    Variable definition extracted from PRD.

    Variables are used to store and pass data throughout the flow.
    """
    name: str
    type: VariableType
    description: str
    source: VariableSource = VariableSource.USER
    required: bool = False
    default: Any = None
    options: Optional[List[str]] = None
    validation_rules: List[ValidationRule] = field(default_factory=list)
    source_node_id: Optional[str] = None  # Which node sets this variable
    persist: bool = True
    collection_mode: str = "explicit"  # explicit or deducible

    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = VariableType.from_string(self.type)
        if isinstance(self.source, str):
            self.source = VariableSource(self.source)

    def to_insait_dict(self) -> Dict[str, Any]:
        """Convert to INSAIT variable format."""
        return {
            "name": self.name,
            "type": self.type.value,
            "default": self.default,
            "description": self.description,
            "required": self.required,
            "persist": self.persist,
            "source": self.source.value,
            "source_node_id": self.source_node_id,
            "collection_mode": self.collection_mode,
            "validation_rules": [
                {"type": r.type, **r.params, "message": r.message}
                for r in self.validation_rules
            ],
            "options": self.options,
            "allowed_file_types": None,
            "max_file_size_mb": None,
        }


@dataclass
class APIParameter:
    """Parameter definition for an API endpoint."""
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None


@dataclass
class APIExtraction:
    """Extraction rule for API response data."""
    variable_name: str
    response_path: str  # JSONPath or XPath
    extraction_type: str = "jsonpath"  # jsonpath or xpath
    description: str = ""


@dataclass
class APIEndpoint:
    """
    API endpoint definition extracted from PRD.

    Represents an external API that the agent needs to call.
    """
    name: str
    description: str
    function_name: str  # Used as tool_id in INSAIT
    method: HTTPMethod = HTTPMethod.POST
    endpoint: str = ""
    base_url: Optional[str] = None
    parameters: List[APIParameter] = field(default_factory=list)
    request_body_template: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    extractions: List[APIExtraction] = field(default_factory=list)
    error_codes: Dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    retry_count: int = 0

    def __post_init__(self):
        if isinstance(self.method, str):
            self.method = HTTPMethod(self.method.upper())

    @property
    def required_parameters(self) -> List[APIParameter]:
        return [p for p in self.parameters if p.required]


@dataclass
class BusinessRule:
    """
    Business rule extracted from PRD.

    Represents conditional logic that affects multiple features.
    """
    id: str
    name: str
    description: str
    condition: str  # Natural language or expression
    action: str     # What to do when condition is met
    applies_to: List[str] = field(default_factory=list)  # Feature IDs
    priority: int = 0  # Higher = more important

    def applies_to_feature(self, feature_id: str) -> bool:
        """Check if this rule applies to a specific feature."""
        return not self.applies_to or feature_id in self.applies_to


@dataclass
class FlowStep:
    """
    Single step in a feature's flow.

    Represents one action or decision point in the flow.
    """
    order: int
    type: FlowStepType
    description: str
    details: Dict[str, Any] = field(default_factory=dict)

    # Optional references
    variable_name: Optional[str] = None  # For collect/set_variable steps
    api_name: Optional[str] = None       # For api_call steps
    condition: Optional[str] = None      # For condition steps
    next_on_success: Optional[int] = None  # Step order on success
    next_on_failure: Optional[int] = None  # Step order on failure

    def __post_init__(self):
        if isinstance(self.type, str):
            self.type = FlowStepType(self.type.lower())


@dataclass
class UserStory:
    """User story associated with a feature."""
    id: str  # e.g., "US-001"
    description: str
    acceptance_criteria: List[str] = field(default_factory=list)


@dataclass
class Feature:
    """
    Feature definition extracted from PRD.

    A feature represents a distinct capability of the agent,
    like authentication, policy lookup, or human handoff.
    """
    id: str  # e.g., "F-01"
    name: str
    description: str
    phase: int = 1
    channel: Channel = Channel.BOTH
    source: str = ""  # Where this feature was defined (for traceability)

    # User stories
    user_stories: List[UserStory] = field(default_factory=list)

    # Flow definition
    flow_steps: List[FlowStep] = field(default_factory=list)
    flow_text: Optional[str] = None  # Original text flow (Text channel)
    flow_audio: Optional[str] = None  # Original audio flow (Voice channel)

    # References
    variables_used: List[str] = field(default_factory=list)
    apis_used: List[str] = field(default_factory=list)
    rules_applied: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # Other feature IDs

    # Acceptance criteria and DoD
    acceptance_criteria: List[str] = field(default_factory=list)
    definition_of_done: List[str] = field(default_factory=list)
    implementation_requirements: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.channel, str):
            self.channel = Channel.from_string(self.channel)

    @property
    def has_text_flow(self) -> bool:
        return self.channel in (Channel.TEXT, Channel.BOTH)

    @property
    def has_voice_flow(self) -> bool:
        return self.channel in (Channel.VOICE, Channel.BOTH)

    @property
    def estimated_node_count(self) -> int:
        """Estimate number of nodes needed for this feature."""
        # Rough estimate: each flow step ~2 nodes average
        return max(len(self.flow_steps) * 2, 1)


@dataclass
class AgentMetadata:
    """
    Agent-level metadata extracted from PRD.

    Contains high-level information about the agent being created.
    """
    name: str
    description: str
    language: str = "en-US"
    channel: Channel = Channel.VOICE
    version: str = "1.0"
    phase: int = 1

    # Additional metadata
    owner: Optional[str] = None
    created_date: Optional[str] = None
    last_updated: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.channel, str):
            self.channel = Channel.from_string(self.channel)


@dataclass
class ParsedPRD:
    """
    Complete parsed PRD structure.

    This is the main output of the parsing phase and input to generation.
    Contains all information extracted from the PRD document.
    """
    # Original content
    raw_content: str
    source_file: Optional[str] = None

    # Parsed components
    metadata: AgentMetadata = field(default_factory=lambda: AgentMetadata(name="Agent", description=""))
    features: List[Feature] = field(default_factory=list)
    variables: List[Variable] = field(default_factory=list)
    apis: List[APIEndpoint] = field(default_factory=list)
    business_rules: List[BusinessRule] = field(default_factory=list)

    # Computed properties
    complexity: Complexity = Complexity.SIMPLE

    # Parsing metadata
    parsed_at: str = field(default_factory=lambda: datetime.now().isoformat())
    parser_version: str = "1.0"
    parse_warnings: List[str] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Auto-calculate complexity
        self.complexity = self._calculate_complexity()

    def _calculate_complexity(self) -> Complexity:
        """Calculate PRD complexity based on features and estimated nodes."""
        feature_count = len(self.features)
        estimated_nodes = self.estimated_node_count

        if feature_count <= 3 and estimated_nodes <= 10:
            return Complexity.SIMPLE
        elif feature_count <= 10 and estimated_nodes <= 50:
            return Complexity.MEDIUM
        elif feature_count <= 20 and estimated_nodes <= 100:
            return Complexity.COMPLEX
        else:
            return Complexity.ENTERPRISE

    @property
    def feature_count(self) -> int:
        """Number of features in the PRD."""
        return len(self.features)

    @property
    def estimated_node_count(self) -> int:
        """Estimate total nodes needed for all features."""
        # Base: start + end nodes
        base = 2
        # Add nodes from each feature
        feature_nodes = sum(f.estimated_node_count for f in self.features)
        return base + feature_nodes

    @property
    def has_api_integrations(self) -> bool:
        """Whether the PRD requires API integrations."""
        return len(self.apis) > 0

    @property
    def requires_voice(self) -> bool:
        """Whether any feature requires voice channel."""
        return any(f.has_voice_flow for f in self.features)

    @property
    def requires_text(self) -> bool:
        """Whether any feature requires text channel."""
        return any(f.has_text_flow for f in self.features)

    def get_feature_by_id(self, feature_id: str) -> Optional[Feature]:
        """Get a feature by its ID."""
        return next((f for f in self.features if f.id == feature_id), None)

    def get_features_by_channel(self, channel: Channel) -> List[Feature]:
        """Get features that support a specific channel."""
        return [f for f in self.features if f.channel in (channel, Channel.BOTH)]

    def get_variable_by_name(self, name: str) -> Optional[Variable]:
        """Get a variable by its name."""
        return next((v for v in self.variables if v.name == name), None)

    def get_api_by_name(self, name: str) -> Optional[APIEndpoint]:
        """Get an API endpoint by its name or function name."""
        return next(
            (a for a in self.apis if a.name == name or a.function_name == name),
            None
        )

    def get_rules_for_feature(self, feature_id: str) -> List[BusinessRule]:
        """Get all business rules that apply to a feature."""
        return [r for r in self.business_rules if r.applies_to_feature(feature_id)]

    def get_feature_dependencies(self, feature_id: str) -> List[Feature]:
        """Get features that the given feature depends on."""
        feature = self.get_feature_by_id(feature_id)
        if not feature:
            return []
        return [
            f for f in self.features
            if f.id in feature.dependencies
        ]

    def get_dependent_features(self, feature_id: str) -> List[Feature]:
        """Get features that depend on the given feature."""
        return [
            f for f in self.features
            if feature_id in f.dependencies
        ]

    def get_all_variable_names(self) -> Set[str]:
        """Get all variable names used across features."""
        names = set(v.name for v in self.variables)
        for feature in self.features:
            names.update(feature.variables_used)
        return names

    def validate(self) -> List[str]:
        """
        Validate the parsed PRD for consistency.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check for duplicate feature IDs
        feature_ids = [f.id for f in self.features]
        if len(feature_ids) != len(set(feature_ids)):
            errors.append("Duplicate feature IDs found")

        # Check for duplicate variable names
        var_names = [v.name for v in self.variables]
        if len(var_names) != len(set(var_names)):
            errors.append("Duplicate variable names found")

        # Check feature dependencies exist
        all_feature_ids = set(feature_ids)
        for feature in self.features:
            for dep_id in feature.dependencies:
                if dep_id not in all_feature_ids:
                    errors.append(f"Feature {feature.id} depends on non-existent feature {dep_id}")

        # Check API references exist
        api_names = set(a.name for a in self.apis) | set(a.function_name for a in self.apis)
        for feature in self.features:
            for api_name in feature.apis_used:
                if api_name not in api_names:
                    errors.append(f"Feature {feature.id} references non-existent API {api_name}")

        return errors

    def summary(self) -> str:
        """Get a summary string of the parsed PRD."""
        return (
            f"PRD: {self.metadata.name}\n"
            f"  Complexity: {self.complexity.value}\n"
            f"  Features: {self.feature_count}\n"
            f"  Variables: {len(self.variables)}\n"
            f"  APIs: {len(self.apis)}\n"
            f"  Business Rules: {len(self.business_rules)}\n"
            f"  Est. Nodes: {self.estimated_node_count}"
        )
