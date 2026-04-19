## _About this document_

This is my (Joe Strout's) development log for PixelClaw.  It's not going to be a detailed log of everything added each day, because that gets long and tedious and is better done by Claude (who is also writing most of the code); see [PROGRESS.md](PROGRESS.md) for that.

Instead, this document is a place for me to record my thoughts, ideas, and design decisions, so that if I come back to the project after a break, I can pick up right where I left off.  If anybody else comes along and finds these thoughts interesting, well that's great too.

## Apr 16 2026

Today was the first day of the project, and holy cows, we got a _lot_ done today.  From nothing, we now have a powerful image editor that can do arbitrary transformations on a single image, split an image into multiple images, and combine multiple images into one.  In testing I've done things like: crop this texture image to match the size of that other one, then copy its alpha over to this one, now soften the edge by applying a slight blur, and then take the three open documents and combine them into one horizontal strip.

It's not always perfect; I'm currently using the gpt-5.4-nano model, the smallest and dumbest of the current GPT series, and sometimes it makes a mistake.  But, we keep adding examples to the instructions, which helps a lot, and making the tools easier to use (like allowing it to use "active" as a special document name rather than having to get the name right).  And at least for changes within an image, we can always undo to any revision -- and this too is very natural; you can say "throw out those size changes" or "revert back to the beginning" or "undo that, and let's try this instead".

One thing we don't yet have is support for undoing the close of a document (or documents).  We should tuck closed documents away somewhere hidden, and give the user some way to bring them back when one was closed by mistake.

I want to keep the UI minimal, because the whole _point_ of a voice interface is that you no longer need to poke around in tool palettes and menus.  But I still have a bunch of things I want to add:

- Document buttons in the header bar: open, close, save
- Pointer modes: grab/drag, point, line, rect

The idea on the references is, the could draw a line and ask the LLM "how long is this line?"  Or maybe we should just display that somewhere automatically, but then the user could say "rotate the image so that this line is straight".  Or they could draw a rectangle and say "extract this into its own image" or click somewhere and say "what's the average color near this point?"

And, we haven't started getting into hooking up more powerful image models.  I'd like to roll in SAM for segmentation, so we can automatically separate foreground from background (or one object from another; here too reference points will be useful).  And image-generation models to create new images from a description.  (The OpenAI platform APIs support image generation, and apparently image editing too; gpt-image-1.5 is best quality, and gpt-image-1-mini is cheaper.)

Oh man, even sticking to OpenAI's image editing platform gives us some powerful abilities: "make this look like watercolor" or "change this to nighttime".  It also does masked inpainting or outpainting.  It can replace a shirt with a jacket, remove an object from the background, and do other fancy things.  It does not seem to support background segmentation directly, though -- their own cookbooks use SAM to do that, and then pass the resulting mask into gpt-image for inpainting/outpainting.

So, a good near-term goal would be to get SAM and gpt-image hooked up; these two together should create some real magic.


## Apr 17 2026

I hooked up gpt-image today, and associated tools (along with some other new tools like rotate and soft_threshold).  It's working really well.  You can use PixelClaw a lot like you'd use ChatGPT, just telling it to create and alter images; but then you also have access to the simpler transformations (resizing, scaling, etc.).  We also hooked up a package called rembg, specialized for removing backgrounds; that works really well too.

The value proposition would get even stronger if we added some basic editing tools as well, similar to at least what GraphicConverter provides.  Maybe the buttons at the top include an "Edit" button; when you click that, editing tools appear, and you get a more fine-grained undo/redo stack while still working on just one version of the image.  Then you click the same button again to close the editing session, or use an LLM command, and it commits that version and starts a new one.

I haven't hooked up SAM yet because it's not really useful until we have some interactive tools, some way to point.  Of course the simple way would be to just pass the pixel coordinates the mouse is over along with any command, so then we can say things like "what is the color here" or (with SAM plus edit_image) "remove this object".  When we do this, we need to look at newer/lighter variants (MobileSAM or EfficientSAM).

We might want to also include GroundingDINO, a language-object detection model.  But it's too large to be practical as a local model; we'd need to find an online version via Roboflow, Replicate, or HuggingFace.  I don't love requiring the user to get another account and API key, though.  And neither Claude nor I can really think of a good use case for it.

One big step up for today: control+S or command+S pops up a native "Save As" dialog, and lets you save your image to disk.  So I've started actually using PixelClaw for real purposes today.  Neat!

I've started talking to Claude about options for a "pixelate" tool, since the obvious flow (posterize and scale, or scale and quantize) don't produce great results.  This is apparently not a well-solved problem, or at least good solutions are not widely known.  I'll dig deeper.

(I tried Retro Diffusion, but it didn't work very well; see the retro-diffusion branch in git.)


## Apr 18 2026

I hooked in the Pyxelate library (https://github.com/sedthh/pyxelate), and I'm quite pleased with the results.  It does the best job of anything I've tried this week.

Then I added a separate_layers tool that I'm quite proud of; it can take a cartoon-style drawing, with strong lines around colored areas, and separate it into "ink", "color", and "background" layers.  The ink layer looks like a coloring book.  If we had the editing tools, you could then paint in the color layer, leaving the ink intact, and then reassemble it.  (I say "layer" but for now they're really separate documents; we don't yet have the concept of image layers.)

Then added a posterize tool.  Ours is, I feel, better than the standard posterize tool even in apps like Affinity Photo; it does a blend first to reduce speckle before finding the reduced palette, and then also does a despeckle operation afterwards to eliminate isolated pixels.  The result is a much smoother posterization.

I've added a test_images folder with some standard images to work with, of several different kinds.  It's amazing what these tools can do — I took an image of a woman in the rain (including rain streaks in front of her face), removed the rain, removed the background, generated a jungle background, and then put the woman in the jungle.  All very easy!

I'm proceeding today mostly by testing and fixing whatever jumps out at me.  Soon I'll need to get more organized about it, but for now this is as good a method as any, given the deep backlog of desireable features.  Added now:

- Query and Trim tools
- smarter background detection in Inspect tool
- simple markdown rendering for the speech bubbles
- an indeterminate progress indicator during long tasks
- mouseover info (pixel position and color), and click to insert position/color into the chat
- Open, Save, and Close buttons (with shortcuts), and tools to let the agent do these

Note that I've chosen to employ a simple on-disk backup strategy against unintended data loss: when we save a file, if a file already exists there, we look for a .bak version of the file.  If we don't find it, then we move the existing file to there.  If it does, then we leave it alone and just overwrite the existing file.  The idea here is that you'll get one backup of each image you start monkeying with, which will preserve it in its original state, and no amount of monkeying in PixelClaw will then clobber it.  You'd have to go in and delete the backup file yourself.

I think tomorrow I'll hook up a speech (STT and TTS) interface, and then record our first demo video.  It already does a lot, and we may as well start getting feedback from other potential users.

I started playing around with TTS just a bit, using [supertonic](https://supertone-inc.github.io/supertonic-py).  The speech sounds good most of the time, but it just gives up and fails entirely when encountering something like `=` in the text, does not do a consistently good job with numbers like 1024, and if you ask it to go faster than the (plodding) 1.0 speed, it frequently drops syllables or words.  So, I might need to look elsewhere.  A good overview of free TTS models can be found [here](https://github.com/0xSojalSec/free-voice-clone).

On the bright side, I've long wanted a chance to try adding some sort of audio modulation to synthesized voices so we can hear when a speaker is AI.  I experimented with both a ring modulation, and a very short echo.  The ring mod produces very much "Star Wars Droid" voices; kind of fun, but also a bit jarring and probably harder to understand, especially in a noisy environment.  However the echo sounds good -- it's pleasant and very intelligible, but still easily recognizable.  The only concern there is that room reverberation might mimic the effect, but I think that would be pretty rare.  I should probably write this up as its own GitHub project or blog post (or both) and try to promote it as a standard.




