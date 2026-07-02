window.addEventListener('DOMContentLoaded', () => {
  const title = document.title;
  if (!title.includes('MyLife')) {
    document.title = `MyLife | ${title}`;
  }
});

(function () {
  const speech = window.speechSynthesis;

  function speak(text, options = {}) {
    if (!text || typeof text !== 'string') {
      return;
    }
    if (!speech || typeof SpeechSynthesisUtterance === 'undefined') {
      console.warn('Speech synthesis is not supported in this browser.');
      return;
    }

    speech.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = options.lang || 'en-US';
    utterance.rate = options.rate || 0.95;
    utterance.pitch = options.pitch || 1.0;

    const voices = speech.getVoices();
    if (options.voiceName && voices.length > 0) {
      const selected = voices.find((voice) => voice.name === options.voiceName);
      if (selected) {
        utterance.voice = selected;
      }
    }

    speech.speak(utterance);
  }

  function cancel() {
    if (speech) {
      speech.cancel();
    }
  }

  const api = { speak, cancel };
  window.MyLifeTTS = api;
  if (window.parent) {
    window.parent.MyLifeTTS = api;
  }
})();
