# Worlds built with code

**Worlds built with code: Blender, Python, Unreal Engine 5 & AI.**
The scripts behind the videos of the [Procedural Arthur](https://www.youtube.com/@ProceduralArthur) YouTube channel, one folder per episode.

| # | Episode | Preview | Video | Code |
|---|---|---|---|---|
| 01 | Ilhinha, the channel mascot: from an AI drawing to a 3D character, fixed with Blender Python | <img src="01-ilhinha-mascot/images/ilhinha_turntable.gif" width="200" alt="Ilhinha turning around, veins pulsing"> | https://youtu.be/dvrbTwH31JI | [01-ilhinha-mascot](01-ilhinha-mascot/) |
| 02 | I gave an AI agent Unreal Engine 5.8: the terrain generator it wrote in plain Python | <img src="images/02-ai-agent-unreal.gif" width="260" alt="The island the AI agent built in Unreal 5.8, with Seed walking on the beach"> | https://youtu.be/6mfvdNNykww | [02-ai-agent-unreal](02-ai-agent-unreal/) |
| 03 | 200 lines of Python made this landscape | <img src="03-python-landscape/images/seeds.gif" width="260" alt="The same script with nine different seeds"> | https://youtu.be/-TVunsf7klQ | [03-python-landscape](03-python-landscape/) |
| 04 | I gave my AI agent real assets: it planted 124,966 plants in Unreal 5.8, then crashed the editor | <img src="images/04-real-assets.gif" width="260" alt="Same cameras before and after the session: slopes, forest floor and reeds"> | https://youtu.be/lZH6nyIS61g | no code folder (the agent wrote it inside the Unreal project) |
| 05 | AI made my drone in 3D. It couldn't fly: propellers that spin true, and a swept-volume collision check | <img src="05-seed-propellers/images/seed_rig.gif" width="260" alt="Seed's rig: propellers spinning on their own axes"> | https://youtu.be/WJsC8znyZXU | [05-seed-propellers](05-seed-propellers/) |
| 06 | My ground script broke. My AI agent fixed it 23 times: a ground kit applied to the island in Unreal 5.8 | <img src="images/06-clay-to-rock.gif" width="260" alt="Before and after: the island slopes go from clay to scanned rock"> | https://youtu.be/4oOlxy6dPa4 | no code folder (the kit script lives inside the Unreal project) |

More episodes will be added as they come out.

## How to use

Every folder has its own README with the steps from the video, the Blender version it was tested on and the exact
command line. The scripts run headless (`blender -b ... --python ...`) on the CPU, so you do not need a GPU.

## License

Code: [MIT](LICENSE). Images, renders and the Ilhinha character are **not** under the MIT license
(all rights reserved); see [NOTICE.md](NOTICE.md).
