
/* FINAL AGENT CLICK INTERACTION
   Click 1: Explanation inside bubble
   Click 2: Decision with color
   Click 3: Close / next recorded round
*/

let agentClickStage = {};
let agentReviewIndex = {};

const previousResetStatuses = resetStatuses;

resetStatuses = function () {
  previousResetStatuses();
  agentClickStage = {};
  agentReviewIndex = {};
};

// Short, genuine explanation from recorded evaluation.
function shortAgentSpeech(name, evaluation) {
  const reason = String(evaluation.reason || '')
    .replace(/\s+/g, ' ')
    .trim();

  const firstSentence =
    reason.match(/^.+?[.!?](?=\s|$)/)?.[0] || reason;

  let summary = firstSentence;

  if (name === 'Creative') {
    const option = (baseCase?.options || []).find(
      o => o.option_id === evaluation.option_id
    );

    const quality = option?.quality_score;
    const minimum = baseCase?.case?.required_quality_min;

    if (quality != null && minimum != null) {
      const comparison =
        ` Quality: ${quality}/100 vs ${minimum}/100.`;

      summary = summary.slice(
        0,
        Math.max(30, 125 - comparison.length)
      ).trimEnd();

      summary += comparison;
    }
  }

  if (name === 'Finance') {
    summary = financeSummary(evaluation);
  }

  if (summary.length > 135) {
    summary = summary.slice(0, 132).trimEnd() + '…';
  }

  return summary;
}

// Replace presentation only; all Python decisions remain real.
renderAgents = function () {
  const root = $('agents');
  root.replaceChildren();

  agentNames.forEach(name => {
    const stage = agentClickStage[name] || 0;
    const isSelected = selectedAgent === name;
    const showReason = replayReady && isSelected && stage === 1;
    const showVerdict = replayReady && isSelected && stage === 2;

    const evaluations = evaluationsFor(name);
    const index = agentReviewIndex[name] || 0;
    const evaluation = evaluations[index % (evaluations.length || 1)];

    const holder = document.createElement('div');
    holder.className = 'agent';

    if (isSelected) holder.classList.add('selected');

    if (showVerdict && evaluation) {
      holder.classList.add(
        evaluation.approved ? 'accepted' : 'rejected'
      );
    } else {
      holder.classList.add('idle');
    }

    const bubble = document.createElement('div');
    bubble.className = 'bubble';

    bubble.style.setProperty(
      'font-size', '13px', 'important'
    );
    bubble.style.lineHeight = '1.3';

    if (!replayReady) {
      bubble.textContent = activeJob
        ? 'Evaluating...'
        : 'Click me after running a scenario';

    } else if (showReason && evaluation) {
      bubble.textContent =
        shortAgentSpeech(name, evaluation);

    } else if (showVerdict && evaluation) {
      bubble.textContent = evaluation.approved
        ? '✓ Accepted'
        : '✕ Rejected';

    } else {
      bubble.textContent = 'Click me';
    }

    // Neutral purple before the second click.
    if (!showVerdict) {
      bubble.style.setProperty(
        'background', '#292044', 'important'
      );
      bubble.style.setProperty(
        'border-color', 'var(--accent)', 'important'
      );
    } else {
      bubble.style.setProperty(
        'background',
        evaluation.approved ? '#176846' : '#862b50',
        'important'
      );
      bubble.style.setProperty(
        'border-color',
        evaluation.approved ? '#70e6a5' : '#ff8eae',
        'important'
      );
    }

    const button = document.createElement('button');
    button.type = 'button';

    const robot = document.createElement('div');
    robot.className = 'robot';

    const label = document.createElement('span');
    label.className = 'name';
    label.textContent = `${name} Agent`;

    const state = document.createElement('div');
    state.className = 'state';

    if (showVerdict && evaluation) {
      state.textContent =
        `● ${evaluation.approved ? 'Accepted' : 'Rejected'}` +
        ` · ${evaluation.option_id}`;

      state.style.setProperty(
        'background',
        evaluation.approved ? '#176846' : '#862b50',
        'important'
      );

    } else if (showReason) {
      state.textContent = '● Explaining';

    } else if (activeJob) {
      state.textContent = '● Processing';

    } else if (replayReady) {
      state.textContent = '● Click me';

    } else {
      state.textContent = '● Idle';
    }

    if (!showVerdict) {
      state.style.setProperty(
        'background', '#493765', 'important'
      );
      state.style.setProperty(
        'color', '#ffffff', 'important'
      );
    }

    button.append(robot, label, state);
    button.addEventListener(
      'click', () => handleAgentClick(name)
    );

    holder.append(bubble, button);
    root.append(holder);
  });
};

// No explanation panel. Only the robot bubble changes.
handleAgentClick = function (name) {
  if (activeJob || !replayReady || !latestResult) {
    return;
  }

  clearExplanation();
  clearRevealTimer();

  const evaluations = evaluationsFor(name);
  if (!evaluations.length) return;

  if (selectedAgent !== name) {
    selectedAgent = name;
    agentClickStage = { [name]: 1 };

  } else if (agentClickStage[name] === 1) {
    // Second click reveals the real verdict.
    agentClickStage[name] = 2;

  } else {
    // Third click closes and prepares the next round.
    agentReviewIndex[name] =
      ((agentReviewIndex[name] || 0) + 1) %
      evaluations.length;

    selectedAgent = null;
    agentClickStage = {};
  }

  renderAgents();
};

// Also remove any old explanation panel.
clearExplanation();
renderAgents();

