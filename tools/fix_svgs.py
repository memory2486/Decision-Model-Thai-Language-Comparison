"""Replace the two pipeline SVGs in `build_report_html.py` with corrected geometry.

A one-off repair, kept so the change is reviewable rather than a silent binary
edit. The first SVG version's labels overflowed their boxes: SVG text does not
wrap, and the box widths were guessed, so at roughly 7.5 px per character for
11 px monospace several lines were wider than the shape holding them and spilled
over the neighbouring box and past the viewBox edge.

Every width below is derived from the text it holds, with the budget stated so
the next edit can check itself:

* 12 px semibold sans-serif title: ~7.0 px per character
* 11 px monospace subtitle: ~7.5 px per character (conservative)
* usable width = box width - 28 (14 px padding each side)

Replacement is by line range rather than by matching text, because the blocks
are long and exact-match replacement of them is brittle.
"""

from __future__ import annotations

import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "tools", "build_report_html.py")

#: (first line index, last line index exclusive) of each `<svg ...>...</svg>`,
#: 0-indexed, as the file stood when this script was written.
SVG1_RANGE = (339, 424)
SVG2_RANGE = (432, 491)

SVG1 = '''<svg viewBox="0 0 1000 480" role="img"
     aria-label="Runtime routing pipeline from user request through supervisor, one typed choice question, a selected backend, confidence normalisation and a fail-closed gate">
  <defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
            orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--faint)"/>
    </marker>
  </defs>

  <text class="flow-label" x="0" y="14">RUNTIME — ONE TYPED CHOICE QUESTION PER REQUEST</text>

  <rect class="box box-a" x="0" y="30" width="160" height="56" rx="8"/>
  <text class="lbl-t" x="14" y="52">User request</text>
  <text class="lbl-s" x="14" y="70">Thai or English</text>

  <rect class="box" x="196" y="30" width="184" height="56" rx="8"/>
  <text class="lbl-t" x="210" y="52">Supervisor.enrich</text>
  <text class="lbl-s" x="210" y="70">context &middot; files</text>

  <rect class="box" x="416" y="30" width="224" height="56" rx="8"/>
  <text class="lbl-t" x="430" y="52">Router.buildRequest</text>
  <text class="lbl-s" x="430" y="70">exactly ONE question</text>

  <path class="edge" d="M160 58 H192"/>
  <path class="edge" d="M380 58 H412"/>

  <text class="flow-label" x="0" y="126">BACKENDS — SELECTED BY model &middot; ONE PROCESS EACH</text>

  <rect class="box box-v" x="0" y="146" width="258" height="94" rx="8"/>
  <text class="lbl-t" x="14" y="168">laya-auto — Router</text>
  <text class="lbl-s" x="14" y="186">picks english | multilingual</text>
  <text class="lbl-s" x="14" y="203">the only key that reads Thai</text>
  <text class="lbl-s" x="14" y="220">kept because it CAN read Thai</text>

  <rect class="box" x="292" y="146" width="252" height="94" rx="8"/>
  <text class="lbl-t" x="306" y="168">laya-en / laya-ml</text>
  <text class="lbl-s" x="306" y="186">a checkpoint, directly</text>
  <text class="lbl-s" x="306" y="203">no script detection</text>
  <text class="lbl-s" x="306" y="220">laya-en is the control</text>

  <rect class="box box-g" x="584" y="146" width="250" height="94" rx="8"/>
  <text class="lbl-t" x="598" y="168">openthai</text>
  <text class="lbl-s" x="598" y="186">SystemOneClient, bf16</text>
  <text class="lbl-s" x="598" y="203">choice &middot; score &middot; noul</text>
  <text class="lbl-s" x="598" y="220">reports abstain</text>

  <path class="edge" d="M528 86 V142"/>

  <text class="flow-label" x="0" y="268">NORMALISE — THE SAME CODE FOR BOTH MODELS</text>

  <rect class="box box-w" x="0" y="284" width="336" height="88" rx="8"/>
  <text class="lbl-t" x="14" y="306">answer_confidence = raw max(p)</text>
  <text class="lbl-s" x="14" y="324">the thresholdable quantity</text>
  <text class="lbl-s" x="14" y="341">identical for both models</text>

  <rect class="box" x="372" y="284" width="312" height="88" rx="8"/>
  <text class="lbl-t" x="386" y="306">confidence = 1 &minus; H(p)/log k</text>
  <text class="lbl-s" x="386" y="324">what BOTH APIs call "confidence"</text>
  <text class="lbl-s" x="386" y="341">not calibrated &middot; not thresholdable</text>

  <rect class="box" x="720" y="284" width="280" height="88" rx="8"/>
  <text class="lbl-t" x="734" y="306">native_* kept verbatim</text>
  <text class="lbl-s" x="734" y="324">Laya: temperature-scaled max-p</text>
  <text class="lbl-s" x="734" y="341">OpenThai: none &middot; abstain slot</text>

  <path class="edge" d="M336 328 H368"/>
  <path class="edge" d="M684 328 H716"/>
  <path class="edge" d="M129 240 V280"/>

  <text class="flow-label" x="0" y="400">GATE — FAILS CLOSED</text>

  <rect class="box box-g" x="0" y="416" width="250" height="48" rx="8"/>
  <text class="lbl-t" x="14" y="445">&ge; 0.8 &rarr; delegate</text>

  <rect class="box box-w" x="284" y="416" width="250" height="48" rx="8"/>
  <text class="lbl-t" x="298" y="445">0.5–0.8 &rarr; clarify</text>

  <rect class="box box-w" x="568" y="416" width="250" height="48" rx="8"/>
  <text class="lbl-t" x="582" y="445">&lt; 0.5 or absent &rarr; refuse</text>

  <path class="edge" d="M125 372 V412"/>
</svg>'''

SVG2 = '''<svg viewBox="0 0 1000 230" role="img"
     aria-label="Benchmark pipeline from authored items through expansion and evaluation to a merged report and a regression gate">
  <defs>
    <marker id="arrow2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
            orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--faint)"/>
    </marker>
  </defs>
  <text class="flow-label" x="0" y="14">BENCHMARK — ONE PROCESS PER BACKEND, MERGED, THEN GATED</text>

  <rect class="box box-a" x="0" y="34" width="196" height="64" rx="8"/>
  <text class="lbl-t" x="14" y="56">focused_items.jsonl</text>
  <text class="lbl-s" x="14" y="74">36 items &rarr; 68 rows</text>
  <text class="lbl-s" x="14" y="91">EN + TH parallel</text>

  <rect class="box" x="234" y="34" width="200" height="64" rx="8"/>
  <text class="lbl-t" x="248" y="56">expand &times; backends</text>
  <text class="lbl-s" x="248" y="74">ordered by model block</text>
  <text class="lbl-s" x="248" y="91">one load per switch</text>

  <rect class="box box-v" x="472" y="34" width="210" height="64" rx="8"/>
  <text class="lbl-t" x="486" y="56">DecisionRunner.predict</text>
  <text class="lbl-s" x="486" y="74">satisfies laya.evals</text>
  <text class="lbl-s" x="486" y="91">one subprocess per model</text>

  <rect class="box box-g" x="720" y="34" width="280" height="64" rx="8"/>
  <text class="lbl-t" x="734" y="56">laya.evals.evaluate</text>
  <text class="lbl-s" x="734" y="74">slice by language &amp; model</text>
  <text class="lbl-s" x="734" y="91">ECE &middot; AURC &middot; sel@80</text>

  <path class="edge" d="M196 66 H230" marker-end="url(#arrow2)"/>
  <path class="edge" d="M434 66 H468" marker-end="url(#arrow2)"/>
  <path class="edge" d="M682 66 H716" marker-end="url(#arrow2)"/>

  <rect class="box" x="0" y="138" width="208" height="64" rx="8"/>
  <text class="lbl-t" x="14" y="160">results/focused.json</text>
  <text class="lbl-s" x="14" y="178">360 case records</text>
  <text class="lbl-s" x="14" y="195">the raw evidence</text>

  <rect class="box box-w" x="246" y="138" width="236" height="64" rx="8"/>
  <text class="lbl-t" x="260" y="160">merge_reports</text>
  <text class="lbl-s" x="260" y="178">re-aggregates from cases</text>
  <text class="lbl-s" x="260" y="195">not a mean of means</text>

  <rect class="box" x="520" y="138" width="212" height="64" rx="8"/>
  <text class="lbl-t" x="534" y="160">report.md / .html</text>
  <text class="lbl-s" x="534" y="178">cross-slices, flips,</text>
  <text class="lbl-s" x="534" y="195">disagreements, advice</text>

  <rect class="box box-g" x="770" y="138" width="230" height="64" rx="8"/>
  <text class="lbl-t" x="784" y="160">baseline &rarr; gate</text>
  <text class="lbl-s" x="784" y="178">0 pass &middot; 1 regressed</text>
  <text class="lbl-s" x="784" y="195">2 : not a comparison</text>

  <path class="edge" d="M860 98 V134" marker-end="url(#arrow2)"/>
  <path class="edge" d="M208 170 H242" marker-end="url(#arrow2)"/>
  <path class="edge" d="M482 170 H516" marker-end="url(#arrow2)"/>
  <path class="edge" d="M732 170 H766" marker-end="url(#arrow2)"/>
</svg>'''


def main() -> None:
    text = io.open(TARGET, encoding="utf-8").read()
    lines = text.split("\n")

    before1 = "\n".join(lines[SVG1_RANGE[0]:SVG1_RANGE[1]])
    before2 = "\n".join(lines[SVG2_RANGE[0]:SVG2_RANGE[1]])
    assert before1.startswith('<svg viewBox="0 0 1000 470"'), before1[:60]
    assert before1.rstrip().endswith("</svg>"), before1[-40:]
    assert before2.startswith('<svg viewBox="0 0 1000 250"'), before2[:60]
    assert before2.rstrip().endswith("</svg>"), before2[-40:]

    # Higher index first, so the earlier replacement cannot shift the later range.
    lines[SVG2_RANGE[0]:SVG2_RANGE[1]] = SVG2.split("\n")
    lines[SVG1_RANGE[0]:SVG1_RANGE[1]] = SVG1.split("\n")

    io.open(TARGET, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    print("replaced both SVGs in %s" % TARGET)


if __name__ == "__main__":
    main()
