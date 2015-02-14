//

var roster = angular.module('rosterApp', [
	'restangular',
	'ui.bootstrap',
	'ui.router',
]);


roster.config(function(RestangularProvider) {
	var base = window.location.pathname
	base = base.slice(-1) == '/' ? base : base + '/';
	RestangularProvider.setBaseUrl(base + 'api');
	RestangularProvider.addResponseInterceptor(function(data, operation, what, url, response, deferred) {
		return data.items;
	});
});
roster.config(function($stateProvider, $urlRouterProvider) {
	$urlRouterProvider.otherwise('/today');
	$stateProvider
		.state('page', {
			url: '',
			templateUrl: 'static/partials/page.html',
		})
		.state('page.today', {
			url: '/today',
			templateUrl: 'static/partials/today.html',
			controller: 'DayController',
			resolve: {
				rosterRest: function(Restangular, $filter, $rootScope) {
					$rootScope.resolving = true;
					var day = $rootScope.status.today;
					var resource = Restangular.all('roster/' + $filter('date')(day, "yyyy-MM-dd'T'"));
					return resource.getList().then(function(entries) {
						$rootScope.resolving = false;
						return {
							day: day,
							entries: entries,
							resource: resource,
						}
					});
				},
			},
		})
		.state('page.day', {
			url: '/day/{day:[^/]*}',
			templateUrl: 'static/partials/today.html',
			controller: 'DayController',
			resolve: {
				rosterRest: function(Restangular, $filter, $stateParams) {
					var day = $stateParams.day;
					var resource = Restangular.all('roster/' + $filter('date')(day, "yyyy-MM-dd'T'"));
					return resource.getList().then(function(entries) {
						return {
							day: day,
							entries: entries,
							resource: resource,
						}
					});
				},
			},
		})
		.state('page.settings', {
			url: '/settings',
			templateUrl: 'static/partials/settings.html',
			controller: 'SettingsController',
			resolve: {
				settingsRest: function(Restangular) {
					var resource = Restangular.all('settings');
					return resource.getList().then(function(entries) {
						return {
							entries: entries,
							resource: resource,
						}
					});
				},
			},
		})
		.state('page.admin-users', {
			url: '/admin-users',
			templateUrl: 'static/partials/admin-users.html',
			controller: 'AdminUsersController',
			resolve: {
				adminUsersRest: function(Restangular) {
					var resource = Restangular.all('users');
					return resource.getList().then(function(entries) {
						return {
							entries: entries,
							resource: resource,
						}
					});
				},
			},
		});
});
/*
 * Override standard view switching to only allow the management views if the
 * logged in user is an admin.
 * http://stackoverflow.com/questions/22537311/angular-ui-router-login-authentication
 */
roster.run(function($state, $rootScope, $urlRouter, $log) {
	$rootScope.$log = $log;
	$rootScope.$state = $state;
	$rootScope.$on('$stateChangeStart', function(evt, toState, toStateParms) {
		if (toState.name.slice(0, 'admin'.length) == 'admin') {
			if ($rootScope.status && $rootScope.status.admin_user) {
				console.log("admin view OK");
				return;
			}
			console.log("redirecting to home view");
			$state.transitionTo('page.today');
		}
	});
});


/*
 * Controller for the main application view; the view shows the navigation. All actual
 * functionality is contained in the subviews.
 */
roster.controller('MainController', function(Restangular, $scope, $rootScope, $state, $timeout) {
	var resource = Restangular.all('status');
	var updateTimeout;
	var startUpdateTimer = function() {
		if (updateTimeout) {
			$timeout.cancel(updateTimeout);
		}
		updateTimeout = $timeout(update, 15*60*1000);
	}
	var update = function() {
		resource.get(1).then(function(items) {
			$scope.status = items[0];
			$rootScope.status = items[0];
			startUpdateTimer();
			if ($state.current.name == '' || $state.is('') || $state.is('page')) {
				$state.transitionTo('page.today');
			}
		});
	};
	/*
	 * On state transitions, show a spinner while the state is resolved.  The spinner
	 * is shown only after 1/4s to avoid unnecessary flickering.
	 */
	var spinnerTimer;
	var spinnerTimerStart = function() {
		if (spinnerTimer) {
			$timeout.cancel(spinnerTimer);
		}
		spinnerTimer = $timeout(function() {
			$rootScope.loading = true;
		}, 250);
	}
	$scope.$on('$stateChangeStart', function(event, toState, toParams, fromState, fromParams) {
		if (toState.resolve) {
			spinnerTimerStart();
		}
	});
	$scope.$on('$stateChangeSuccess', function(event, toState, toParams, fromState, fromParams) {
		if (toState.resolve) {
			if (spinnerTimer) {
				$timeout.cancel(spinnerTimer);
			}
			$rootScope.loading = false;
		}
	});
	update();
});


/*
 * Display and allow adding to the roster for a particular day.
 */
roster.controller('DayController', function($scope, $rootScope, $timeout, rosterRest) {
	$scope.day = rosterRest.day;
	$scope.will_sums = {
		will_open: 0,
		will_service: 0,
		will_close: 0,
	}
	var updateCounts = function() {
		$scope.will_sums.will_open = 0;
		$scope.will_sums.will_service = 0;
		$scope.will_sums.will_close = 0;
		$scope.rosterentries.map(function(e) {
			if (e.will_open)
				$scope.will_sums.will_open++;
			if (e.will_service)
				$scope.will_sums.will_service++
			if (e.will_close)
				$scope.will_sums.will_close++;
		});
		var e = $scope.myself;
		if (e.will_open)
			$scope.will_sums.will_open++;
		if (e.will_service)
			$scope.will_sums.will_service++
		if (e.will_close)
			$scope.will_sums.will_close++;
	}
	var processEntries = function(entries) {
		$scope.myself = {
			name: $rootScope.status.name,
			user_id: $rootScope.status.user_id,
			will_open: false,
			will_service: false,
			will_close: false,
			comment: '',
			id: undefined
		}
		$scope.rosterentries = [];
		entries.map(function(e) {
			if (e.user_id == $rootScope.status.user_id) {
				$scope.myself = e;
			} else {
				if (e.will_open || e.will_service || e.will_close ||
						e.comment != '') {
					$scope.rosterentries.push(e);
				}
			}
		});
		updateCounts();
		$scope.$watch('myself.will_open', debounceUpdate);
		$scope.$watch('myself.will_service', debounceUpdate);
		$scope.$watch('myself.will_close', debounceUpdate);
		$scope.$watch('myself.comment', debounceUpdate);
			startUpdateTimer();
	}
	var update = function() {
		rosterRest.resource.getList().then(processEntries);
	}
	$scope.update = update;
	$scope.save = function() {
		entry = $scope.myself;
		if (entry.id) {
			entry.put();
		} else {
			rosterRest.resource.post(entry).then(function() {
				update();
			});
		}
	}
	var updateTimeout;
	var startUpdateTimer = function() {
		if (updateTimeout) {
			$timeout.cancel(updateTimeout);
		}
		updateTimeout = $timeout(update, 5*60*1000);
	};
	var debounceTimeout;
	var debounceUpdate = function(newVal, oldVal, scope) {
		if (newVal === oldVal) {
			return;
		}
		updateCounts();
		if (debounceTimeout) {
			$timeout.cancel(debounceTimeout);
		}
		debounceTimeout = $timeout($scope.save, 1000);
		startUpdateTimer();
	};
	processEntries(rosterRest.entries);
});


/*
 * Allow users to change their password and certain other settings.
 */
roster.controller('SettingsController', function($scope, $modal, settingsRest) {
	$scope.user = settingsRest.entries[0];
	$scope.update = function() {
		settingsRest.resource.getList().then(function(entries) {
			$scope.user = entries[0];
		});
	}
	$scope.save = function() {
		$scope.user.put();
	}
	$scope.changePassword = function() {
		var passwords = {
			old: '',
			new1: '',
			new2: '',
		};
		var modalInstance = undefined;
		var modalOpen = function(alert) {
			modalInstance = $modal.open({
				templateUrl: 'changePassword.html',
				controller: function($scope, passwords, alert) {
					$scope.ok = modalInstance.close;
					$scope.cancel = modalInstance.dismiss;
					$scope.passwords = passwords;
					$scope.alert = alert;
				},
				backdrop: 'static',
				resolve: {
					passwords: function() { return passwords; },
					alert: function() { return alert; },
				}
			});
		}
		var modalThen = function() {
			console.log("saving: " + passwords.old);
			if (passwords.new1 != passwords.new2) {
				modalOpen('Die beiden neuen Passwörter müssen übereinstimmen.');
			}
			settingsRest.resource.post(passwords).then(function() {
			}, function(response) {
				modalOpen(response.data.msg);
				modalInstance.result.then(modalThen);
			});
		}
		modalOpen('');
		modalInstance.result.then(modalThen);
	}
});


/*
 * Admins can create, update, and delete users.
 */
roster.controller('AdminUsersController', function($scope, $modal, adminUsersRest) {
	$scope.userentries = adminUsersRest.entries;
	var update = function() {
		adminUsersRest.resource.getList().then(function(entries) {
			$scope.userentries = entries;
		});
	}
	var user = {};
	var modalAlerts = [];
	var modalOpen = function() {
		return $modal.open({
			templateUrl: 'useredit.html',
			controller: 'UserEditModalController',
			backdrop: 'static',
			resolve: {
				user: function() {
					return user;
				},
				alerts: function() {
					return modalAlerts;
				}
			}
		})
	};
	var modalInstance = undefined;
	var modalInstanceSave = function() {};
	var modalInstanceThen = function(selectedItem) {
		modalInstanceSave().then(function() {
			update();
		}, function(response) {
			modalAlerts = []
			modalAlerts.push({msg: response.data.msg,
				type: 'danger'});
			console.log(response);
			modalInstance = modalOpen();
			modalInstance.result.then(modalInstanceThen);
		});
	};
	$scope.useradd = function() {
		user = {
			'id': undefined,
			'name': '',
			'email': '',
			'password': '',
			'admin_user': false,
		}
		modalAlerts = []
		modalInstance = modalOpen();
		modalInstanceSave = function() {
			console.log(user);
			return adminUsersRest.resource.post(user);
		}
		modalInstance.result.then(modalInstanceThen);
	}
	$scope.useredit = function(aUser) {
		user = aUser.clone();
		modalAlerts = []
		modalInstance = modalOpen();
		modalInstanceSave = function() {
			return user.put();
		}
		modalInstance.result.then(modalInstanceThen);
	}
	$scope.userdelete = function(user) {
		var modalInstance = $modal.open({
			templateUrl: 'userdelete.html',
			controller: 'UserDeleteModalController',
			user: user,
			resolve: {
				user: function() {
					return user;
				}
			}
		});
		modalInstance.result.then(function(selectedItem) {
			user.remove().then(function() {
				update();
			});
		}, function() {
			console.log("aborted");
		});
	}
	update();
});
roster.controller("UserEditModalController", function($scope, $modalInstance, user, alerts) {
	$scope.user = user;
	$scope.alerts = alerts;
	$scope.ok = function() {
		console.log("foo");
		$modalInstance.close(0);
	};
	$scope.cancel = function() {
		$modalInstance.dismiss('cancel');
	};
	$scope.closeAlert = function(index) {
		$scope.alerts.splice(index, 1);
	}
});
roster.controller("UserDeleteModalController", function($scope, $modalInstance, user) {
	$scope.user = user;
	$scope.selected = 0;
	$scope.ok = function() {
		$modalInstance.close();
	};
	$scope.cancel = function() {
		$modalInstance.dismiss('cancel');
	};
});
