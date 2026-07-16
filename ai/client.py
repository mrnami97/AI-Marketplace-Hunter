import json
import logging
import re
from typing import Any

from openai import OpenAI

from ai.schemas import ListingAIAnalysis


logger = logging.getLogger(__name__)


class PikkAPIError(RuntimeError):
    """Base error raised by the PIKKAPI client."""


class PikkAPIAuthError(PikkAPIError):
    """The configured PIKKAPI token was rejected."""


class PikkAPIUsageError(PikkAPIError):
    """The token has no usable plan or remaining quota."""


def _remove_markdown_fence(
    text: str,
) -> str:
    value = text.strip()

    fenced_match = re.search(
        r"```(?:json)?\s*(.*?)```",
        value,
        flags=(
            re.IGNORECASE
            | re.DOTALL
        ),
    )

    if fenced_match:
        return fenced_match.group(1).strip()

    return value


def _extract_json_object(
    text: str,
) -> dict[str, Any]:
    """
    Extract the first complete JSON object from a gateway response.

    Some compatible gateways may prepend or append ordinary text, for example:

        We{"category": "GPU", ...}

    json.JSONDecoder.raw_decode() lets us parse the valid object without
    requiring the whole response string to contain JSON only.
    """
    cleaned = _remove_markdown_fence(
        text
    )

    decoder = json.JSONDecoder()
    last_error: Exception | None = None

    for index, character in enumerate(
        cleaned
    ):
        if character != "{":
            continue

        candidate = cleaned[index:]

        try:
            value, _end = (
                decoder.raw_decode(
                    candidate
                )
            )

        except json.JSONDecodeError as error:
            last_error = error
            continue

        if isinstance(value, dict):
            return value

    if last_error is not None:
        raise PikkAPIError(
            "PIKKAPI response contained no "
            "complete JSON object."
        ) from last_error

    raise PikkAPIError(
        "PIKKAPI response contained no "
        "JSON object."
    )


class AIClient:
    """
    PIKKAPI client using its documented OpenAI-compatible Responses API.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        base_url: str,
    ) -> None:
        self.model = model
        self.base_url = (
            base_url.rstrip("/")
        )

        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=timeout_seconds,
            max_retries=2,
        )

    def analyze_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> ListingAIAnalysis:
        schema = (
            ListingAIAnalysis
            .model_json_schema()
        )

        reinforced_system_prompt = (
            system_prompt
            + "\n\nIMPORTANT OUTPUT RULES:\n"
            + "- Return exactly one JSON object.\n"
            + "- Do not add introductory words.\n"
            + "- Do not add markdown fences.\n"
            + "- Do not add explanations after the JSON."
        )

        try:
            response = (
                self.client.responses.create(
                    model=self.model,
                    input=[
                        {
                            "role": "system",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": (
                                        reinforced_system_prompt
                                    ),
                                }
                            ],
                        },
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": user_prompt,
                                }
                            ],
                        },
                    ],
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": (
                                "listing_ai_analysis"
                            ),
                            "strict": True,
                            "schema": schema,
                        }
                    },
                    temperature=0.0,
                )
            )

        except Exception as error:
            message = str(error)
            lowered = message.lower()

            if (
                "401" in lowered
                or "unauthorized" in lowered
                or "invalid api key" in lowered
            ):
                raise PikkAPIAuthError(
                    "PIKKAPI rejected the "
                    "API token."
                ) from error

            if (
                "403" in lowered
                or "usage not included"
                in lowered
                or "insufficient"
                in lowered
                or "quota" in lowered
            ):
                raise PikkAPIUsageError(
                    "PIKKAPI usage is "
                    "unavailable for this "
                    "token or plan."
                ) from error

            raise PikkAPIError(
                message
            ) from error

        response_text = (
            getattr(
                response,
                "output_text",
                "",
            )
            or ""
        ).strip()

        if not response_text:
            fragments: list[str] = []

            for output_item in getattr(
                response,
                "output",
                [],
            ):
                for content_item in getattr(
                    output_item,
                    "content",
                    [],
                ):
                    text_value = getattr(
                        content_item,
                        "text",
                        None,
                    )

                    if text_value:
                        fragments.append(
                            str(text_value)
                        )

            response_text = "\n".join(
                fragments
            ).strip()

        if not response_text:
            raise PikkAPIError(
                "PIKKAPI returned no text."
            )

        try:
            json_object = (
                _extract_json_object(
                    response_text
                )
            )

            return (
                ListingAIAnalysis
                .model_validate(
                    json_object
                )
            )

        except Exception as error:
            preview = response_text[:300]

            logger.warning(
                "Could not parse PIKKAPI "
                "structured output. Preview: %r",
                preview,
            )

            if isinstance(
                error,
                PikkAPIError,
            ):
                raise

            raise PikkAPIError(
                "PIKKAPI returned invalid "
                "structured JSON."
            ) from error

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            logger.debug(
                "PIKKAPI client close "
                "not required.",
                exc_info=True,
            )
