function Init(){
   AddBlok('<h1>SberGate version: 2.0.9</h1>')
   AddBlok('<a href="index.html">Перейти к настройкам СберАгента</a></p>')
   AddBlok('<a href="SberGate.log">Скачать SberGate.log</a></p>')
   AddBlok('<h2>Команды:</h2>')
//   AddBlok('<button class="btn">&#128465; Удалить</button>')
   AddBlok('<button id="DB_delete" onclick="RunCmd(this.id)">   &#128465; Удалить базу устройств</button><button id="exit" onclick="RunCmd(this.id)">Выход</button>')
   AddBlok('<h2>Устройства:</h2>','alert')
   apiGet()
}
function AddBlok(str,CN){
   let div = document.createElement('div');
   if (CN) {div.className = CN;}
   div.innerHTML = str;
   let el = document.getElementById('root');
   if (el) {el.append(div)}
//   document.body.append(div);
}

function RunCmd(id,opt){
   alert(id+':'+opt);
   let s = {'command':id}
   apiSend(s,'/api/v2/command');
}


function ChangeDev(d){
   var t={};   var s={};
   t[d.dataset.id]={}
   t[d.dataset.id]['enabled']=d.checked;
   s['devices']=[];
   s['devices'].push(t);
   
   // Update global state
   if (window.devicesList && window.devicesList[d.dataset.id]) {
       window.devicesList[d.dataset.id]['enabled'] = d.checked;
   }

   apiSend(s,'/api/v2/devices');
   //console.dir(d)
//   console.log(d.dataset.id);
//   console.log(d.checked);
}

function UpdateDeviceList(d, sortKey = null, sortAsc = true) {
    let f = {'enabled': 'Включено', 'home': 'Дом', 'room': 'Комната', 'id': 'ID', 'name': 'Имя', 'entity_type': 'Тип', 'States': 'Состояния'};
    let table = document.getElementById('devices');
    
    if (table) {
        table.innerHTML = '';
    } else {
        table = document.createElement('table');
        table.id = 'devices';
        let pel = document.getElementById('root');
        pel.append(table);
    }

    // Convert object to array for sorting
    let devicesArray = [];
    for (let id in d) {
        let device = d[id];
        device.id = id; // Ensure ID is part of the object
        devicesArray.push(device);
    }

    // Sort if key is provided
    if (sortKey) {
        devicesArray.sort((a, b) => {
            let valA = a[sortKey];
            let valB = b[sortKey];
            
            // Handle States separately or as string
            if (sortKey === 'States') {
                valA = JSON.stringify(valA || {});
                valB = JSON.stringify(valB || {});
            }
            
            // Handle null/undefined
            valA = (valA === undefined || valA === null) ? '' : valA;
            valB = (valB === undefined || valB === null) ? '' : valB;

            if (valA < valB) return sortAsc ? -1 : 1;
            if (valA > valB) return sortAsc ? 1 : -1;
            return 0;
        });
    }

    let thead = document.createElement('thead');
    let tbody = document.createElement('tbody');

    let thead_row = document.createElement('tr');
    for (let k in f) {
        let el = document.createElement('th');
        el.innerHTML = f[k];
        el.style.cursor = 'pointer';
        el.onclick = () => {
            // Toggle sort direction if clicking the same header
            let newSortAsc = (sortKey === k) ? !sortAsc : true;
            UpdateDeviceList(d, k, newSortAsc);
        };
        // Add arrow indicator
        if (sortKey === k) {
            el.innerHTML += sortAsc ? ' &#9650;' : ' &#9660;';
        }
        thead_row.append(el);
    }
    thead.appendChild(thead_row);

    for (let device of devicesArray) {
        let tbody_row = document.createElement('tr');
        for (let k in f) {
            let el = document.createElement('td');
            let r;
            switch (k) {
                case 'id':
                    r = device.id;
                    break;
                case 'enabled':
                    if (device[k]) {
                        r = '<input type="checkbox" data-id="' + device.id + '" checked onchange=ChangeDev(this)>';
                    } else {
                        r = '<input type="checkbox" data-id="' + device.id + '" onchange=ChangeDev(this)>';
                    }
                    break;
                case 'States':
                    if (device['States']) {
                        r = JSON.stringify(device['States']);
                    } else {
                        r = '';
                    }
                    break;
                default:
                    r = device[k];
                    break;
            }
            el.innerHTML = r;
            tbody_row.append(el);
        }
        tbody.appendChild(tbody_row);
    }

    table.appendChild(thead);
    table.appendChild(tbody);
}

function Res_Processing(Res){
   console.log(Res);
}

function apiGet_url(url){
   let xhr = new XMLHttpRequest();
   xhr.open('GET', url);
   xhr.send();
   xhr.onload = function() {
      if (xhr.status == 200) {
//         alert(`Готово, получили ${xhr.response.length} байт`);
           Res_Processing(xhr.response);
      } else { // если всё прошло гладко, выводим результат
         console.log(`Ошибка ${xhr.status}: ${xhr.statusText}`); // Например, 404: Not Found
      }
   };
   xhr.onprogress = function(event) {
      if (event.lengthComputable) {
         console.log(`Получено ${event.loaded} из ${event.total} байт`);
      } else {
         console.log(`Получено ${event.loaded} байт`); // если в ответе нет заголовка Content-Length
      }
   };
   xhr.onerror = function() {
      console.log("Запрос не удался");
   };
}

function apiGet(){
   let xhr = new XMLHttpRequest();
   xhr.open('GET', '/api/v2/devices');
   xhr.send();
   xhr.onload = function() {
      if (xhr.status == 200) {
//         alert(`Готово, получили ${xhr.response.length} байт`);
         window.devicesList = JSON.parse(xhr.response)['devices'];
         UpdateDeviceList(window.devicesList)
      } else { // если всё прошло гладко, выводим результат
         console.log(`Ошибка ${xhr.status}: ${xhr.statusText}`); // Например, 404: Not Found
      }
   };
   xhr.onprogress = function(event) {
      if (event.lengthComputable) {
         console.log(`Получено ${event.loaded} из ${event.total} байт`);
      } else {
         console.log(`Получено ${event.loaded} байт`); // если в ответе нет заголовка Content-Length
      }
   };
   xhr.onerror = function() {
      console.log("Запрос не удался");
   };
}

function apiSend(d,api){ //console.log(d);
   if (typeof api == "undefined" ) { api = '/api/v2/devices';}
   let xhr = new XMLHttpRequest();
   let json = JSON.stringify(d);
   xhr.open('POST', api, true);
   xhr.setRequestHeader('Content-type', 'application/json; charset=utf-8');
   ///xhr.onreadystatechange = ...;
   xhr.send(json);
}