import time
from django.db import connections
from django.utils.encoding import force_str
from string import Template


class LoadTimeMiddleware:
	FORCE_DEBUG_CURSOR_DB_ATTRIBUTE = 'force_debug_cursor'

	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		start_time = time.perf_counter_ns()

		connection_initial_force_debug_cursor_values = (
			self.get_connection_initial_force_debug_cursor_values()
		)
		self.enable_force_debug_for_all_connections()
		response = self.get_response(request)

		try:
			if self.check_if_response_can_be_rendered(response):
				response = response.render()

			load_details = self.build_load_details(start_time)
			total_ms = load_details['total_ms']
			database_ms = load_details['database_ms']
			no_of_database_queries = load_details['no_of_database_queries']
			app_ms = load_details['app_ms']

			self.add_load_time_headers_to_response(
				response=response,
				total_ms=total_ms,
				database_ms=database_ms,
				no_of_database_queries=no_of_database_queries,
				app_ms=app_ms,
			)

			if not self.check_if_html_can_be_injected_in_response(response):
				return response

			html_to_inject = self.build_load_time_badge_html(
				total_ms=total_ms,
				database_ms=database_ms,
				no_of_database_queries=no_of_database_queries,
				app_ms=app_ms,
			)
			response_with_injected_html = self.inject_html_into_response(
				response=response,
				html_to_inject=html_to_inject
			)
		except Exception:
			return response
		finally:
			self.restore_force_debug_cursor_values_for_connections(
				connection_initial_force_debug_cursor_values
			)

		return response_with_injected_html

	@classmethod
	def get_connection_initial_force_debug_cursor_values(cls):
		return {
			alias: getattr(connections[alias], cls.FORCE_DEBUG_CURSOR_DB_ATTRIBUTE, False)
			for alias in connections
		}

	@classmethod
	def enable_force_debug_for_all_connections(cls):
		for alias in connections:
			setattr(
				connections[alias],
				cls.FORCE_DEBUG_CURSOR_DB_ATTRIBUTE,
				True
			)

	@staticmethod
	def check_if_response_can_be_rendered(response):
		return hasattr(response, 'render') and callable(response.render)

	@classmethod
	def restore_force_debug_cursor_values_for_connections(cls, initial_values):
		for alias in connections:
			setattr(
				connections[alias],
				cls.FORCE_DEBUG_CURSOR_DB_ATTRIBUTE,
				initial_values.get(alias, False)
			)

	@classmethod
	def build_load_details(cls, start_time):
		total_ms = cls.get_elapsed_time_in_ms(start_time)

		database_load_details = cls.get_database_load_details()
		database_ms = database_load_details['ms']

		return {
			'total_ms': total_ms,
			'database_ms': database_ms,
			'no_of_database_queries': database_load_details['no_of_queries'],
			'app_ms': max(total_ms - database_ms, 0.0)
		}

	@staticmethod
	def get_elapsed_time_in_ms(start_time):
		return (time.perf_counter_ns() - start_time) / 1_000_000.0

	@classmethod
	def get_database_load_details(cls):
		database_load_details = {
			'ms': 0.0,
			'no_of_queries': 0
		}

		for alias in connections:
			connection = connections[alias]
			for query in getattr(connection, 'queries', []):
				try:
					database_load_details['ms'] += cls.get_query_time_in_ms(query)
					database_load_details['no_of_queries'] += 1
				except Exception:
					pass

		return database_load_details

	@staticmethod
	def get_query_time_in_ms(query):
		return float(query.get('time', 0.0)) * 1000.0

	@classmethod
	def add_load_time_headers_to_response(
		cls,
		response,
		total_ms,
		database_ms,
		no_of_database_queries,
		app_ms
	):
		cls.set_server_timing_header_to_response(
			response=response,
			total_ms=total_ms,
			database_ms=database_ms,
			app_ms=app_ms,
		)
		cls.set_custom_load_time_total_time_header_to_response(
			response=response,
			total_ms=total_ms
		)
		cls.set_custom_load_time_database_time_header_to_response(
			response=response,
			database_ms=database_ms
		)
		cls.set_custom_load_time_no_of_database_queries_header_to_response(
			response=response,
			no_of_database_queries=no_of_database_queries
		)
		cls.set_custom_load_time_app_time_header_to_response(
			response=response,
			app_ms=app_ms
		)

	@staticmethod
	def set_server_timing_header_to_response(response, total_ms, database_ms, app_ms):
		response['Server-Timing'] = (
			f'total;dur={total_ms}, '
			f'db;dur={database_ms}, '
			f'app;dur={app_ms}'
		)

	@staticmethod
	def set_custom_load_time_total_time_header_to_response(response, total_ms):
		response['X-LoadTime-TotalMs'] = str(total_ms)

	@staticmethod
	def set_custom_load_time_database_time_header_to_response(response, database_ms):
		response['X-LoadTime-DatabaseMs'] = str(database_ms)

	@staticmethod
	def set_custom_load_time_no_of_database_queries_header_to_response(response, no_of_database_queries):
		response['X-LoadTime-NoOfDatabaseQueries'] = str(no_of_database_queries)

	@staticmethod
	def set_custom_load_time_app_time_header_to_response(response, app_ms):
		response['X-LoadTime-AppMs'] = str(app_ms)

	@classmethod
	def check_if_html_can_be_injected_in_response(cls, response):
		if 'text/html' not in cls.get_response_content_type(response):
			return False

		if not hasattr(response, 'content'):
			return False

		try:
			response_text = cls.get_response_text(response)
		except Exception:
			return False

		return '</body>' in response_text.lower()

	@staticmethod
	def get_response_content_type(response):
		return (response.get('Content-Type', '') or '').lower()

	@classmethod
	def get_response_text(cls, response):
		return force_str(
			response.content,
			encoding=cls.get_response_charset(response),
			strings_only=False,
			errors='ingore'
		)

	@staticmethod
	def get_response_charset(response):
		return getattr(response, 'charset', 'utf-8')

	@staticmethod
	def build_load_time_badge_html(total_ms, database_ms, no_of_database_queries, app_ms):
		load_time_badge_html_template = Template("""
<style>
	#load-time-badge, #load-time-panel {
		position: fixed; right: 12px; bottom: 14px; z-index: 2147483647;
		font: 12px/1.2 system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
	}
	#load-time-badge {
		background: #007BFF; color: #fff; border-radius: 999px;
		padding: 6px 26px 6px 10px; cursor: pointer; user-select: none;
		box-shadow: 0 2px 8px rgba(0,0,0,.25);
		position: fixed; right: 12px; bottom: 14px; display: inline-block;
		max-width: fit-content; z-index: 2147483647;
	}
	#load-time-badge:hover {
		background: #0056b3;
	}
	#load-time-badge-close {
		position: absolute; top: 2px; right: 6px; font-size: 10px; line-height: 10px;
		padding: 2px; cursor: pointer; opacity: .8;
	}
	#load-time-badge-close:hover {
		opacity: 1;
	}
	#load-time-panel {
		display: none; min-width: 240px; max-width: 360px; bottom: 46px;
		background: #0d6efd; color: #fff; border-radius: 10px; padding: 10px 12px;
		box-shadow: 0 8px 24px rgba(0,0,0,.35);
	}
	#load-time-panel table {
		width:100%;
		border-collapse: collapse;
	}
	#load-time-panel td {
		padding:4px 2px;
	}
	#load-time-panel td:first-child {
		opacity:.85;
	}
	#load-time-close {
		position: absolute;
		top: 6px;
		right: 8px;
		cursor: pointer;
		opacity: .9;
		color: #fff;
		font-weight: bold;
	}
	#load-time-close:hover {
		color: #cce5ff;
	}
	@media print {
		#load-time-badge, #load-time-panel {
			display:none !important;
		}
	}
</style>

<div id="load-time-badge" title="Click for page timings">
	<span id="lt-badge-total-load">⏱</span>
	<span id="load-time-badge-close">✕</span>
</div>
<div id="load-time-panel" role="dialog" aria-label="Page timings">
	<div id="load-time-close" aria-label="Close">✕</div>
	<table>
		<tr>
			<th colspan="3">Server</th>
			<th rowspan="2">Client</th>
			<th rowspan="2">Total</th>
		</tr>
		<tr>
			<th>App</th>
			<th>DB</th>
			<th>Total</th>
		</tr>
		<tr>
			<td id="lt-server-app-load">$app_ms ms</td>
			<td id="lt-server-db-load">$db_ms ms ($no_of_database_queries queries)</td>
			<td id="lt-server-total-load">$total_ms ms</td>
			<td id="lt-client-load">pending…</td>
			<td id="lt-total-load">pending…</td>
		</tr>
	</table>
</div>

<script>
	(function(){
		var b=document.getElementById('load-time-badge'),
		p=document.getElementById('load-time-panel'),
		x=document.getElementById('load-time-close'),
		bx=document.getElementById('load-time-badge-close'),
		clientEl=document.getElementById('lt-client-load'),
		totalEl=document.getElementById('lt-total-load'),
		badgeEl=document.getElementById('lt-badge-total-load');

		if(!b||!p) return;

		// Toggle panel (ignore clicks on the tiny X)
		b.addEventListener('click', function(e){
			if(e.target && e.target.id === 'load-time-badge-close') return;
			p.style.display = (p.style.display==='block'?'none':'block');
		});
		x && x.addEventListener('click', function(){ p.style.display='none'; });
		bx && bx.addEventListener('click', function(e){
			e.stopPropagation(); if(b) b.remove(); if(p) p.remove();
		});

		function ms(v){ return (v>=0 ? Math.round(v) + ' ms' : 'pending…'); }
		function setClientLoad(){
			try {
				var nav = (performance.getEntriesByType && performance.getEntriesByType('navigation')[0]) || null;
				var totalLoadMs = 0;
				if (nav) {
					// Navigation Timing Level 2
					totalLoadMs = (nav.loadEventEnd || 0) - (nav.startTime || 0);
				} else if (performance.timing) {
					// Legacy Navigation Timing
					var t = performance.timing;
					totalLoadMs = (t.loadEventEnd || 0) - (t.navigationStart || 0);
				}
				var serverMs = parseInt("$total_ms", 10) || 0;
				var clientOnlyMs = Math.max(totalLoadMs - serverMs, 0);

				if (totalEl)  totalEl.textContent  = ms(totalLoadMs);
				if (clientEl) clientEl.textContent = ms(clientOnlyMs);
				if (badgeEl)  badgeEl.textContent  = "⏱ " + ms(totalLoadMs);
			} catch(e) {
				if (totalEl)  totalEl.textContent  = 'n/a';
				if (clientEl) clientEl.textContent = 'n/a';
				if (badgeEl)  badgeEl.textContent  = '⏱ n/a';
			}
		}

		if (document.readyState === 'complete') {
			// page already loaded
			setTimeout(setClientLoad, 0);
		} else {
			// wait for full load
			window.addEventListener('load', function(){ setTimeout(setClientLoad, 0); });
		}
	})();
</script>
		""")

		return load_time_badge_html_template.substitute(
			total_ms=round(total_ms),
			db_ms=round(database_ms),
			app_ms=round(app_ms),
			no_of_database_queries=no_of_database_queries,
		)

	@classmethod
	def inject_html_into_response(cls, response, html_to_inject):
		old_response_text = cls.get_response_text(response)
		new_response_text = cls.inject_html_into_response_text(
			response_text=old_response_text,
			text_to_inject=html_to_inject
		)

		cls.set_response_content(
			response=response,
			response_text=new_response_text,
		)
		cls.delete_content_length_header_from_response(response)

		return response

	@staticmethod
	def inject_html_into_response_text(response_text, text_to_inject):
		index_to_inject_at = response_text.lower().rfind('</body>')

		return (
			response_text[:index_to_inject_at] +
			text_to_inject +
			response_text[index_to_inject_at:]
		)

	@classmethod
	def set_response_content(cls, response, response_text):
		response.content = response_text.encode(
			cls.get_response_charset(response),
			errors='ingore'
		)

	@staticmethod
	def delete_content_length_header_from_response(response):
		if 'Content-Length' in response:
			del response['Content-Length']
