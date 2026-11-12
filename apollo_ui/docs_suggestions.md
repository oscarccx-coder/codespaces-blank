# Apollo Suggestions

Open Chat → Apps → Apollo Suggestions (also in the Everyday app group). The page stores proposed next steps, the self-prompts Apollo wants to research, observed mission references, owner questions, answer history and review status.

When enabled, local reflection waits until Apollo has been idle for five minutes. It attempts reflection at most once an hour and four times per UTC day. It reads up to five recent learning missions, their saved next questions/recall results, and up to eight bounded owner guidance answers. It does not read the screen, other apps, arbitrary files or private chat history. Only a loopback Ollama endpoint and a non-cloud-labelled selected model are allowed. A call has a 60-second deadline and uses the existing local Foundry model lock. Errors are visible; no successful improvement is fabricated.

A quiet chat banner can show an unanswered owner question. It opens Suggestions without changing the conversation, stealing focus or starting work. It is hidden during generation and in temporary chats. Answer when convenient, keep a proposal, or dismiss it. Dismissal/answers survive restarts and duplicate titles do not recreate dismissed items. The inbox has a 50-open-item limit; model-generated questions are limited to two open questions.

Answers are saved locally for future reflection. Optionally select the Memory Bank checkbox to save an explicit owner guidance note for later recall. A failed Memory Bank write does not erase the local answer; the UI reports the failure. No additional personal facts are inferred.

To act on a proposal, review/edit its prompt, authorise public research and click **Edit prompt and start idle research**. This creates an existing until-stop, idle-only practice mission, using normal evidence checks, topic routing, budgets, pause/stop and source permissions. Repeated clicks reconcile the stable suggestion title rather than duplicate the mission. Merely keeping a suggestion never starts work.

The model has only a read-only list-suggestions tool. Proposed text is data, not a command channel or permission grant. Reflection does not train model weights, execute proposed code, purchase anything, grant cloud access, change production code or publish releases. Disable reflection to stop future proposals; existing approved research missions are controlled separately in Practice & learning. The app/PC must remain running.
