import numpy as np

import itertools

import matplotlib
from mpl_toolkits.mplot3d.art3d import Line3DCollection

from sitator.util import PBCCalculator
from sitator.visualization import plotter, plot_atoms, plot_points, layers, DEFAULT_COLORS, set_axes_equal

class SiteNetworkPlotter(object):
    """Plot a ``SiteNetwork``.

    Note that for edges, the average of the edge property for i -> j and j -> i
    is often used for visual clarity; if your edge properties are not almost symmetric,
    the visualization might not be useful.

    Args:
        site_mappings (dict): defines how to show different properties. Each
            entry maps a visual aspect ('marker', 'color', 'size') to the name
            of a site attribute including 'site_type'. The markers can also be
            arbitrary text (key `"text"`) in which case the value can also be a
            2-tuple of an attribute name and a `%` format string.
        edge_mappings (dict): each key maps a visual property ('intensity',
            'color', 'width', 'linestyle') to an edge attribute in the SiteNetwork.
        markers (list of str): What `matplotlib` markers to use for sites.
        plot_points_params (dict): User options for plotting site points.
        minmax_linewidth (2-tuple): Minimum and maximum linewidth to use.
        minmax_edge_alpha (2-tuple): Similar, for edge line alphas.
        minmax_markersize (2-tuple): Similar, for markersize.
        min_color_threshold (float): Minimum (normalized) color intensity for
            the corresponding line to be shown. Defaults to zero, i.e., all
            nonzero edges will be drawn.
        min_width_threshold (float): Minimum normalized edge width for the
            corresponding edge to be shown. Defaults to zero, i.e., all
            nonzero edges will be drawn.
        title (str): Title for the figure.
    """

    DEFAULT_SITE_MAPPINGS = {
        'marker' : 'site_types',
    }

    DEFAULT_MARKERS = ['x', '+', 'v', '<', '^', '>', '*', 'd', 'h', 'p']
    DEFAULT_LINESTYLES = ['--', ':', '-.', '-']

    EDGE_GROUP_COLORS = ['b', 'g', 'm', 'crimson', 'lightseagreen', 'darkorange', 'sandybrown', 'gold', 'hotpink'] + ['gray'] # gray last for -1's

    def __init__(self,
                site_mappings = DEFAULT_SITE_MAPPINGS,
                edge_mappings = {},
                markers = DEFAULT_MARKERS,
                plot_points_params = {},
                minmax_linewidth = (1.5, 7),
                minmax_edge_alpha = (0.15, 0.75),
                minmax_markersize = (20.0, 80.0),
                min_color_threshold = 0.0,
                min_width_threshold = 0.0,
                title = ""):
        self.site_mappings = site_mappings
        assert not ("marker" in site_mappings and "text" in site_mappings)
        self.edge_mappings = edge_mappings
        self.markers = markers
        self.plot_points_params = plot_points_params

        self.minmax_linewidth = minmax_linewidth
        self.minmax_edge_alpha = minmax_edge_alpha
        self.minmax_markersize = minmax_markersize

        self.min_color_threshold = min_color_threshold
        self.min_width_threshold = min_width_threshold

        self.title = title

    @plotter(is3D = True, figsize = (10, 10))
    def __call__(self, sn, *args, **kwargs):
        # -- Plot actual SiteNetwork --
        l = [(plot_atoms,  {'atoms' : sn.static_structure})]
        l += self._site_layers(sn, self.plot_points_params)
        l += self._plot_edges(sn, *args, **kwargs)

        # -- Some visual clean up --
        ax = kwargs['ax']

        ax.set_title(self.title)

        ax.xaxis.pane.fill = False
        ax.yaxis.pane.fill = False
        ax.zaxis.pane.fill = False

        # Now set color to white (or whatever is "invisible")
        ax.xaxis.pane.set_edgecolor('w')
        ax.yaxis.pane.set_edgecolor('w')
        ax.zaxis.pane.set_edgecolor('w')

        # Finally remove axis:
        ax.set_axis_off()

        # -- Put it all together --
        layers(*l, **kwargs)

    def _site_layers(self, sn, plot_points_params, same_normalization = False):
        pts_arrays = {'points' : sn.centers}
        pts_params = {'cmap' : 'winter'}

        # -- Apply mapping
        # - other mappings
        markers = None

        for key in self.site_mappings:
            val = self.site_mappings[key]
            if isinstance(val, tuple):
                val, param = val
            else:
                param = None
            val = getattr(sn, val)
            if key == 'marker':
                if not val is None:
                    markers = val.copy()
                istextmarker = False
            elif key == 'text':
                istextmarker = True
                format_str = "%s" if param is None else param
                format_str = "$" + format_str + "$"
                markers = val.copy()
            elif key == 'color':
                pts_arrays['c'] = val.copy()
                if not same_normalization:
                    self._color_minmax = [np.min(val), np.max(val)]
                    if self._color_minmax[0] == self._color_minmax[1]:
                        self._color_minmax[0] -= 1 # Just to avoid div by zero
                color_minmax = self._color_minmax
                pts_params['norm'] = matplotlib.colors.Normalize(vmin = color_minmax[0], vmax = color_minmax[1])
            elif key == 'size':
                if not same_normalization:
                    self._size_minmax = [np.min(val), np.max(val)]
                    if self._size_minmax[0] == self._size_minmax[1]:
                        self._size_minmax[0] -= 1 # Just to avoid div by zero
                size_minmax = self._size_minmax
                s = val.copy()
                s -= size_minmax[0]
                s /= size_minmax[1] - size_minmax[0]
                s *= self.minmax_markersize[1]
                s += self.minmax_markersize[0]
                pts_arrays['s'] = s
            else:
                raise KeyError("Unknown mapping `%s`" % key)
        # - markers first
        marker_layers = {}

        if markers is None:
            # Just one layer with all points and one marker
            marker_layers[SiteNetworkPlotter.DEFAULT_MARKERS[0]] = np.ones(shape = sn.n_sites, dtype = np.bool)
        else:
            if not istextmarker:
                markers = self._make_discrete(markers)
            unique_markers = np.unique(markers)
            if not same_normalization:
                if istextmarker:
                    self._marker_table = dict(zip(unique_markers, (format_str % um for um in unique_markers)))
                else:
                    if len(unique_markers) > len(self.markers):
                        raise ValueError("Too many distinct values of the site property mapped to markers (there are %i) for the %i markers in `self.markers`" % (len(unique_markers), len(self.markers)))
                    self._marker_table = dict(zip(unique_markers, self.markers[:len(unique_markers)]))

            for um in unique_markers:
                marker_layers[self._marker_table[um]] = (markers == um)

        # -- Do plot
        # If no color info provided, a fallback
        if not 'color' in pts_params and not 'c' in pts_arrays:
            pts_params['color'] = 'k'
        # If no color info provided, a fallback
        if not 's' in pts_params and not 's' in pts_arrays:
            pts_params['s'] = sum(self.minmax_markersize) / 2
        # Add user options for `plot_points`
        pts_params.update(plot_points_params)

        pts_layers = []

        for marker in marker_layers:
            d = {'marker' : marker}
            msk = marker_layers[marker]
            for arr in pts_arrays:
                d[arr] = pts_arrays[arr][msk]
            d.update(pts_params)
            pts_layers.append((plot_points, d))

        return pts_layers

    def _plot_edges(self, sn, ax = None, *args, **kwargs):
        if not 'intensity' in self.edge_mappings:
            return []

        pbcc = PBCCalculator(sn.structure.cell)

        n_sites = sn.n_sites
        centers = sn.centers

        # -- Edge attributes
        all_cs = None
        all_linewidths = None
        all_color = None
        all_groups = None
        # Get value arrays as they exist
        for edgekey in self.edge_mappings:
            edgeval = getattr(sn, self.edge_mappings[edgekey])
            if edgekey == 'intensity':
                all_cs = edgeval.copy()
            elif edgekey == 'width':
                all_linewidths = edgeval.copy()
            elif edgekey == 'group':
                assert edgeval.dtype == np.int
                all_groups = edgeval
            else:
                raise KeyError("Invalid edge mapping key `%s`" % edgekey)

        do_widths = not all_linewidths is None
        do_groups = not all_groups is None

        # - Normalize
        # Ignore values on the diagonal since we ignore them in the loop
        diag_mask = np.ones(shape = all_cs.shape, dtype = np.bool)
        np.fill_diagonal(diag_mask, False)

        self._normalize(all_cs, diag_mask)

        if do_widths:
            self._normalize(all_linewidths, diag_mask)

        # -- Construct Line3DCollection segments

        # Whether an edge has already been added
        done_already = np.zeros(shape = (n_sites, n_sites), dtype = np.bool)
        # For the Line3DCollection
        segments = []
        cs = []
        linewidths = []
        groups = []
        # To plot minimum images that are outside unit cell
        sites_to_plot = []
        sites_to_plot_positions = []

        for i in range(n_sites):
            for j in range(n_sites):
                # No self edges
                if i == j:
                    continue
                # If was already done
                if done_already[i, j]:
                    continue
                # Ignore anything below the threshold
                if all_cs[i, j] <= self.min_color_threshold:
                    continue
                if do_widths and all_linewidths[i, j] <= self.min_width_threshold:
                    continue

                segment = np.empty(shape = (2, 3), dtype = centers.dtype)
                segment[0] = centers[i]
                ptbuf = centers[j].copy()

                # Modified segment[1] in place
                minimg = pbcc.min_image(segment[0], ptbuf)
                was_already_min_img = minimg == 111

                segment[1] = ptbuf

                segments.append(segment)

                # If they are eachother's minimum image, then don't bother plotting
                # j -> i
                if was_already_min_img:
                    done_already[j, i] = True
                else:
                    # We'll plot it
                    sites_to_plot.append(j)
                    sites_to_plot_positions.append(segment[1])

                # The mean
                cs.append(np.mean([all_cs[i, j], all_cs[j, i]]))

                if do_widths:
                    linewidths.append(np.mean([all_linewidths[i, j], all_linewidths[j, i]]))
                if do_groups:
                    # Assumes symmetric
                    groups.append(all_groups[i, j])

                done_already[i, j] = True

        # -- Construct final Line3DCollection
        assert len(cs) == len(segments)

        if len(cs) > 0:
            lccolors = np.empty(shape = (len(cs), 4), dtype = np.float)
            # Group colors
            if do_groups:
                for i in range(len(cs)):
                    if groups[i] >= len(SiteNetworkPlotter.EDGE_GROUP_COLORS) - 1:
                        raise ValueError("Too many groups, not enough group colors")
                    lccolors[i] = matplotlib.colors.to_rgba(SiteNetworkPlotter.EDGE_GROUP_COLORS[groups[i]])
            else:
                lccolors[:] = matplotlib.colors.to_rgba(SiteNetworkPlotter.EDGE_GROUP_COLORS[0])
            # Intensity alpha
            lccolors[:,3] = np.array(cs) * self.minmax_edge_alpha[1]
            lccolors[:,3] += self.minmax_edge_alpha[0]

            if do_widths:
                linewidths = np.asarray(linewidths)
                linewidths *= self.minmax_linewidth[1]
                linewidths += self.minmax_linewidth[0]
            else:
                linewidths = self.minmax_linewidth[1] * 0.5

            lc = Line3DCollection(segments, linewidths = linewidths, colors = lccolors, zorder = -20)
            ax.add_collection(lc)

            # -- Plot new sites
            if len(sites_to_plot) > 0:
                sn2 = sn[sites_to_plot]
                sn2.update_centers(np.asarray(sites_to_plot_positions))
                pts_params = dict(self.plot_points_params)
                pts_params['alpha'] = 0.2
                return self._site_layers(sn2, pts_params, same_normalization = True)
            else:
                return []
        else:
            return []

    def _normalize(self, arr, mask, threshold = 0.001):
        msked = arr[mask]

        min = np.min(msked)
        max = np.max(msked)

        if max - min < threshold:
            return None
        else:
            arr += min
            arr /= min + max

    def _make_discrete(self, arr):
        return np.round(arr).astype(np.int)
