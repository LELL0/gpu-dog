import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js'
import { panel as MainPanel } from 'resource:///org/gnome/shell/ui/main.js'
import GpuDogIndicator from './indicator.js'


export default class GpuDogExtension extends Extension {
	#indicator = null

	enable() {
		this.#indicator = new GpuDogIndicator(this)
		MainPanel.addToStatusArea('gpudog-indicator', this.#indicator)
	}

	disable() {
		this.#indicator?.destroy()
		this.#indicator = null
	}
}
