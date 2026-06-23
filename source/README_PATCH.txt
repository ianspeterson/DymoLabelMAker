Label Station v4.13 refresh/retry + range shortcut patch

Replace these files in your current project:
  app.py
  templates/review.html

Use this MA plugin:
  ma_plugins/LabelStation_PrintFromPatch_V4_8_ObjectList.lua

Changes:
- New MA print requests replace the current pending review job, so if you make a mistake you can resend from MA and the browser will switch to the newest batch.
- Review pages poll for a replacement job and automatically redirect to the latest review batch.
- Added a "Discard this batch" button on the review page.
- MA plugin supports single-label ranges like "201".
- MA plugin supports shortcut ranges like "201 t 203" and "201 t" as aliases for "201 thru 203" and "201 thru".
