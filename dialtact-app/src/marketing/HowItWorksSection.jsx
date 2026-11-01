import React from 'react';
import { BotAnchor } from './ScrollBot';
import { Reveal } from './effects';

const STEPS = [
  ['Connect your number', 'Forward the line you already have, or claim a new one.'],
  ['Teach it your business', 'Upload FAQs, prices and hours. It answers from them, and says so when it can’t.'],
  ['Let it take the calls', 'It books, qualifies and hands the call to a person when one is needed.'],
];

/** The mascot stands on the left and presents the three steps on the right. */
export function HowItWorksSection() {
  return (
    <section
      id="how-it-works"
      className="mk-section"
      aria-labelledby="mk-how-title"
      data-bot-say="Three steps. Most teams are live the same afternoon."
      data-bot-gesture="REACH_RIGHT"
      data-bot-state="LISTENING"
      data-bot-title="How it works"
      data-bot-side="left"
    >
      <div className="mk-container mk-split mk-split--bot-left">
        <div className="mk-split-stage"><BotAnchor /></div>
        <div>
          <h2 id="mk-how-title" className="mk-h2">Live on your line in an afternoon.</h2>
          <ol className="mk-steps">
            {STEPS.map(([title, body], index) => (
              <Reveal as="li" key={title} delay={index * 0.08}>
                <h3>{title}</h3>
                <p>{body}</p>
              </Reveal>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
