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
