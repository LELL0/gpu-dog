# GPU Cat

A GNOME Shell panel cat that runs faster the busier your GPU is.
Fork of [GNOME RunCat](https://github.com/win0err/gnome-runcat) by Sergei Kolesnikov (GPL-3.0); the CPU data source is replaced with a GPU one.

## How usage is measured

| GPU | Source | Root needed |
|---|---|---|
| Intel (i915) | `gt/gt0/rc6_residency_ms` (busy = 1 - idle residency / time) | no |
| Intel (xe) | `device/tile0/gt0/gtidle/idle_residency_ms` | no |
| AMD (amdgpu) | `device/gpu_busy_percent` | no |
| NVIDIA (proprietary) | `nvidia-smi --query-gpu=utilization.gpu` | no |

The cat follows the busiest GPU. A GPU whose `power/runtime_status` is not `active`
is skipped and counted as idle, so on hybrid laptops polling never wakes a sleeping
discrete GPU.

## Install from source

```sh
cd gpu-cat@lell0.github.io
gnome-extensions pack --force -o .. --extra-source=dataProviders --extra-source=resources --extra-source=LICENSE --extra-source=README.md --extra-source=constants.js --extra-source=indicator.js --extra-source=math.js --extra-source=utils.js .
gnome-extensions install --force ../gpu-cat@lell0.github.io.shell-extension.zip
```

Log out and back in (Wayland), then enable "GPU Cat".

## License

GPL-3.0-or-later. Sprites and original code © Sergei Kolesnikov and contributors.
