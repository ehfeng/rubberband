module.exports = {
    entry: {
        app: "./rubberband/static/app/app.jsx",
        rubberband: "./rubberband/static/app/rubberband.jsx"
    },
    output: {
        path: __dirname,
        filename: "./rubberband/static/build/[name].js"
    },
    resolve: {
        extensions: ['', '.js', '.jsx'],
    },
    module: {
        loaders: [
            { test: /\.css$/, loader: "style!css" },
            { test: /\.less$/, loader: "css-loader!less-loader"},
            {
                test: /\.jsx$/,
                loader: "babel-loader",
                query: {
                    presets: ['es2015', 'react']
                }
            }
        ]
    }
};