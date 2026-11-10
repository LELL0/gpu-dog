import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js'
import { panel as MainPanel } from 'resource:///org/gnome/shell/ui/main.js'
import GpuCatIndicator from './indicator.js'


export default class GpuCatExtension extends Extension {
	#indicator = null

	enable() {
		this.#indicator = new GpuCatIndicator(this)
		MainPanel.addToStatusArea('gpucat-indicator', this.#indicator)
	}

	disable() {
		this.#indicator?.destroy()
		this.#indicator = null
	}
}
