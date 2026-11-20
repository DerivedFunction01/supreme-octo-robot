// GENERATED fixture — the mock adapter's segment-feed
// specimen. The blocks below are the output of the
// pipeline's own segmenter (pipeline/workrecord
// lib/derived/segments.py) over FIXTURE_DOCUMENT, the
// exact document the backend tests segment
// (tests/server/test_segments.py) and the contracts
// fixture (contracts/fixtures/entry-segments.json)
// serves. Regenerate by running that segmenter over the
// document — never hand-edit the blocks; a hand-invented
// payload would diverge from the served shape.

import type { FeedSegmentBlock } from "./feeds";

/** The fixture document: fictional field-note content
 *  in the math study's form — prose with inline math, a
 *  numbered display equation, a malformed pair, prices
 *  the inline heuristic keeps literal, a protected code
 *  span, and a fence. */
export const FIXTURE_DOCUMENT: string = "# Field note — residual diagnostics\n\nFor each observation $i$ we record the residual $r_i = y_i - \\hat{y}_i$, the gap\nbetween the measured value and the fitted value. The fit is accepted when the\nresiduals stay small relative to $\\sigma / \\sqrt{n}$.\n\n$$R^2 = 1 - \\frac{\\sum_{i=1}^{n} r_i^2}{\\sum_{i=1}^{n} (y_i - \\bar{y})^2}$$ (1)\n\n## Checks\n\n- The prices $5 and $10 in the log are currency, not math.\n- Inline code like `$\\alpha$` stays literal inside backticks.\n- A broken draft term $\\frac{1}{2$ is missing its closing brace.\n\nThe normal equations collect the moments:\n\n$$\\mathbf{X}^{\\top} \\mathbf{X} \\, \\boldsymbol{\\beta} = \\mathbf{X}^{\\top} \\mathbf{y}$$\n\nA broken display term from the draft:\n\n$$\\frac{\\sum_{i=1}^{n} x_i}{n$$\n\n```text\nSegments never reach inside a fence: $x^2$ stays text here.\n```\n";

/** The segmenter's served blocks for FIXTURE_DOCUMENT. */
export const FIXTURE_SEGMENT_BLOCKS: FeedSegmentBlock[] = [
  {
    "kind": "heading",
    "level": 1,
    "runs": [
      {
        "type": "text",
        "text": "Field note — residual diagnostics"
      }
    ]
  },
  {
    "kind": "paragraph",
    "runs": [
      {
        "type": "text",
        "text": "For each observation "
      },
      {
        "type": "math",
        "source": "i",
        "display": false,
        "valid": true
      },
      {
        "type": "text",
        "text": " we record the residual "
      },
      {
        "type": "math",
        "source": "r_i = y_i - \\hat{y}_i",
        "display": false,
        "valid": true
      },
      {
        "type": "text",
        "text": ", the gap\nbetween the measured value and the fitted value. The fit is accepted when the\nresiduals stay small relative to "
      },
      {
        "type": "math",
        "source": "\\sigma / \\sqrt{n}",
        "display": false,
        "valid": true
      },
      {
        "type": "text",
        "text": "."
      }
    ]
  },
  {
    "kind": "math",
    "source": "R^2 = 1 - \\frac{\\sum_{i=1}^{n} r_i^2}{\\sum_{i=1}^{n} (y_i - \\bar{y})^2}",
    "display": true,
    "valid": true,
    "number": "(1)"
  },
  {
    "kind": "heading",
    "level": 2,
    "runs": [
      {
        "type": "text",
        "text": "Checks"
      }
    ]
  },
  {
    "kind": "list",
    "ordered": false,
    "items": [
      [
        {
          "type": "text",
          "text": "The prices $5 and $10 in the log are currency, not math."
        }
      ],
      [
        {
          "type": "text",
          "text": "Inline code like "
        },
        {
          "type": "code",
          "text": "$\\alpha$"
        },
        {
          "type": "text",
          "text": " stays literal inside backticks."
        }
      ],
      [
        {
          "type": "text",
          "text": "A broken draft term "
        },
        {
          "type": "math",
          "source": "\\frac{1}{2",
          "display": false,
          "valid": false
        },
        {
          "type": "text",
          "text": " is missing its closing brace."
        }
      ]
    ]
  },
  {
    "kind": "paragraph",
    "runs": [
      {
        "type": "text",
        "text": "The normal equations collect the moments:"
      }
    ]
  },
  {
    "kind": "math",
    "source": "\\mathbf{X}^{\\top} \\mathbf{X} \\, \\boldsymbol{\\beta} = \\mathbf{X}^{\\top} \\mathbf{y}",
    "display": true,
    "valid": true
  },
  {
    "kind": "paragraph",
    "runs": [
      {
        "type": "text",
        "text": "A broken display term from the draft:"
      }
    ]
  },
  {
    "kind": "math",
    "source": "\\frac{\\sum_{i=1}^{n} x_i}{n",
    "display": true,
    "valid": false
  },
  {
    "kind": "code",
    "text": "Segments never reach inside a fence: $x^2$ stays text here.",
    "language": "text"
  }
];
