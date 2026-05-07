from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta
import random
import string
import hashlib

app = Flask(__name__)
app.config['SECRET_KEY'] = 'finquantdash_secret_key_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///finquantdash.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

class Institution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    credit_code = db.Column(db.String(18), unique=True, nullable=False)
    type = db.Column(db.String(50))
    industry = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100), unique=True)
    address = db.Column(db.Text)
    admin_name = db.Column(db.String(50))
    admin_phone = db.Column(db.String(20))
    admin_password_hash = db.Column(db.String(128))
    status = db.Column(db.String(20), default='pending')
    review_id = db.Column(db.String(50), unique=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

class VerificationCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), nullable=False)
    code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    usage_count = db.Column(db.Integer, default=0)
    max_attempts = db.Column(db.Integer, default=5)

class LoginAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    ip_address = db.Column(db.String(50))
    success = db.Column(db.Boolean, default=False)
    error_message = db.Column(db.String(200))
    attempt_time = db.Column(db.DateTime, default=datetime.utcnow)

class PasswordResetRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    verification_code = db.Column(db.String(6))
    reset_token = db.Column(db.String(100), unique=True)
    expires_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')
    ip_address = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    user = db.relationship('User', backref=db.backref('reset_requests', lazy=True))

with app.app_context():
    db.create_all()

def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))

def encrypt_data(data):
    return hashlib.sha256(data.encode()).hexdigest()

def generate_reset_token():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))

def check_password_strength(password):
    """检查密码强度"""
    strength = 0
    feedback = []
    
    if len(password) >= 8:
        strength += 1
    else:
        feedback.append('密码长度至少8位')
    
    if len(password) >= 12:
        strength += 1
    else:
        feedback.append('密码长度建议12位以上')
    
    if any(c.isupper() for c in password) and any(c.islower() for c in password):
        strength += 1
    else:
        feedback.append('密码需包含大小写字母')
    
    if any(c.isdigit() for c in password):
        strength += 1
    else:
        feedback.append('密码需包含数字')
    
    if any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
        strength += 1
    else:
        feedback.append('密码建议包含特殊字符')
    
    level = ['弱', '一般', '中等', '强', '非常强']
    return {
        'strength': strength,
        'level': level[min(strength, 4)],
        'feedback': feedback
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember_me = request.form.get('rememberMe')
        
        user = User.query.filter_by(username=username).first()
        
        if user and bcrypt.check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = username
            session['user_type'] = 'user'
            if remember_me:
                session.permanent = True
            
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            log_login_attempt(username, request.remote_addr, True, None)
            return jsonify({'success': True, 'message': '登录成功'})
        else:
            log_login_attempt(username, request.remote_addr, False, '账号或密码错误')
            return jsonify({'success': False, 'message': '账号或密码错误'})
    
    return render_template('index.html', active_tab='login')

@app.route('/sms-login', methods=['GET', 'POST'])
def sms_login():
    if request.method == 'POST':
        phone = request.form['phone']
        code = request.form['code']
        
        verify_code = VerificationCode.query.filter_by(phone=phone).order_by(VerificationCode.created_at.desc()).first()
        
        if verify_code and verify_code.code == code:
            if datetime.utcnow() > verify_code.expires_at:
                return jsonify({'success': False, 'message': '验证码已过期'})
            
            if verify_code.usage_count >= verify_code.max_attempts:
                return jsonify({'success': False, 'message': '验证码使用次数已达上限'})
            
            verify_code.usage_count += 1
            db.session.commit()
            
            user = User.query.filter_by(phone=phone).first()
            if not user:
                user = User(
                    username=f'user_{phone}',
                    password_hash=bcrypt.generate_password_hash(encrypt_data(phone)).decode('utf-8'),
                    email=f'{phone}@example.com',
                    phone=phone
                )
                db.session.add(user)
                db.session.commit()
            
            session['user_id'] = user.id
            session['username'] = user.username
            session['user_type'] = 'user'
            
            return jsonify({'success': True, 'message': '登录成功'})
        else:
            return jsonify({'success': False, 'message': '验证码错误'})
    
    return render_template('index.html', active_tab='sms')

@app.route('/send-sms-code', methods=['POST'])
def send_sms_code():
    phone = request.json.get('phone')
    
    if not phone or not phone.isdigit() or len(phone) != 11:
        return jsonify({'success': False, 'message': '手机号码格式不正确'})
    
    existing_code = VerificationCode.query.filter_by(phone=phone).order_by(VerificationCode.created_at.desc()).first()
    if existing_code and datetime.utcnow() - existing_code.created_at < timedelta(seconds=60):
        return jsonify({'success': False, 'message': '发送过于频繁，请稍后重试'})
    
    code = generate_code(6)
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    
    new_code = VerificationCode(
        phone=phone,
        code=code,
        expires_at=expires_at
    )
    db.session.add(new_code)
    db.session.commit()
    
    print(f"【短信验证码】发送到 {phone}：{code}（有效期5分钟）")
    
    return jsonify({'success': True, 'message': '验证码已发送'})

@app.route('/institution-login', methods=['GET', 'POST'])
def institution_login():
    if request.method == 'POST':
        account = request.form['account']
        password = request.form['password']
        
        institution = Institution.query.filter_by(name=account).first()
        
        if institution and institution.status == 'approved':
            if bcrypt.check_password_hash(institution.admin_password_hash, password):
                session['institution_id'] = institution.id
                session['institution_name'] = institution.name
                session['user_type'] = 'institution'
                
                return jsonify({'success': True, 'message': '机构登录成功'})
        
        return jsonify({'success': False, 'message': '账号或密码错误，或机构未通过审核'})
    
    return render_template('index.html', active_tab='institution')

@app.route('/institution-register', methods=['GET', 'POST'])
def institution_register():
    if request.method == 'POST':
        data = request.form
        
        institution = Institution(
            name=data['instName'],
            credit_code=data['creditCode'],
            type=data['instType'],
            industry=data['instIndustry'],
            phone=data['instPhone'],
            email=data['instEmail'],
            address=data['instAddress'],
            admin_name=data['adminName'],
            admin_phone=data['adminPhone'],
            admin_password_hash=bcrypt.generate_password_hash(data['adminPassword']).decode('utf-8'),
            status='pending',
            review_id=f'REV-{datetime.now().strftime("%Y%m%d%H%M%S")}',
            submitted_at=datetime.utcnow()
        )
        
        db.session.add(institution)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '注册申请已提交，审核结果将通过短信和邮箱通知'})
    
    return render_template('index.html', active_tab='institution_register')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        phone = request.form.get('phone')
        
        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': '用户名已存在'})
        
        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': '邮箱已被注册'})
        
        new_user = User(
            username=username,
            password_hash=bcrypt.generate_password_hash(password).decode('utf-8'),
            email=email,
            phone=phone
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '注册成功，请登录'})
    
    return render_template('index.html', active_tab='register')

def log_login_attempt(username, ip_address, success, error_message):
    attempt = LoginAttempt(
        username=username,
        ip_address=ip_address,
        success=success,
        error_message=error_message
    )
    db.session.add(attempt)
    db.session.commit()

@app.route('/api/check-session')
def check_session():
    if 'user_id' in session:
        return jsonify({'logged_in': True, 'user_type': session.get('user_type')})
    return jsonify({'logged_in': False})

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """忘记密码第一步：验证用户身份"""
    if request.method == 'POST':
        identifier = request.json.get('identifier')
        method = request.json.get('method')  # 'email' or 'phone'
        
        if not identifier or not method:
            return jsonify({'success': False, 'message': '请输入账号信息并选择验证方式'})
        
        # 根据验证方式查找用户
        if method == 'email':
            user = User.query.filter_by(email=identifier).first()
            if not user:
                return jsonify({'success': False, 'message': '该邮箱未注册'})
            target = user.email
            contact_type = '邮箱'
        else:
            user = User.query.filter_by(phone=identifier).first()
            if not user:
                return jsonify({'success': False, 'message': '该手机号未注册'})
            target = user.phone
            contact_type = '手机'
        
        # 检查是否有未完成的重置请求（防止频繁请求）
        existing_request = PasswordResetRequest.query.filter_by(
            user_id=user.id, 
            status='pending',
            expires_at__gt=datetime.utcnow()
        ).first()
        
        if existing_request:
            return jsonify({'success': False, 'message': '已有重置请求处理中，请稍后再试'})
        
        # 生成验证码
        code = generate_code(6)
        expires_at = datetime.utcnow() + timedelta(minutes=15)
        
        # 创建重置请求记录
        reset_request = PasswordResetRequest(
            user_id=user.id,
            email=user.email,
            phone=user.phone,
            verification_code=code,
            reset_token=generate_reset_token(),
            expires_at=expires_at,
            ip_address=request.remote_addr
        )
        db.session.add(reset_request)
        db.session.commit()
        
        # 模拟发送验证码
        print(f"【密码重置验证码】发送到{contact_type} {target}：{code}（有效期15分钟）")
        
        return jsonify({
            'success': True, 
            'message': f'验证码已发送至您的{contact_type}，有效期15分钟',
            'contact_type': contact_type,
            'masked_contact': target[:3] + '****' + target[-4:]
        })
    
    return render_template('index.html')

@app.route('/verify-reset-code', methods=['POST'])
def verify_reset_code():
    """忘记密码第二步：验证验证码"""
    identifier = request.json.get('identifier')
    method = request.json.get('method')
    code = request.json.get('code')
    
    if not identifier or not method or not code:
        return jsonify({'success': False, 'message': '请填写完整信息'})
    
    # 查找用户
    if method == 'email':
        user = User.query.filter_by(email=identifier).first()
    else:
        user = User.query.filter_by(phone=identifier).first()
    
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'})
    
    # 查找有效的重置请求
    reset_request = PasswordResetRequest.query.filter_by(
        user_id=user.id,
        status='pending',
        expires_at__gt=datetime.utcnow()
    ).order_by(PasswordResetRequest.created_at.desc()).first()
    
    if not reset_request:
        return jsonify({'success': False, 'message': '重置请求不存在或已过期'})
    
    if reset_request.verification_code != code:
        return jsonify({'success': False, 'message': '验证码错误'})
    
    # 验证成功，标记请求状态
    reset_request.status = 'verified'
    db.session.commit()
    
    return jsonify({
        'success': True,
        'message': '身份验证成功，请设置新密码',
        'reset_token': reset_request.reset_token
    })

@app.route('/reset-password', methods=['POST'])
def reset_password():
    """忘记密码第三步：设置新密码"""
    reset_token = request.json.get('reset_token')
    new_password = request.json.get('new_password')
    confirm_password = request.json.get('confirm_password')
    
    if not reset_token or not new_password or not confirm_password:
        return jsonify({'success': False, 'message': '请填写完整信息'})
    
    if new_password != confirm_password:
        return jsonify({'success': False, 'message': '两次输入的密码不一致'})
    
    # 检查密码强度
    strength_result = check_password_strength(new_password)
    if strength_result['strength'] < 3:
        return jsonify({
            'success': False,
            'message': f'密码强度不足（当前为{strength_result["level"]}）',
            'feedback': strength_result['feedback']
        })
    
    # 查找有效的重置请求
    reset_request = PasswordResetRequest.query.filter_by(
        reset_token=reset_token,
        status='verified',
        expires_at__gt=datetime.utcnow()
    ).first()
    
    if not reset_request:
        return jsonify({'success': False, 'message': '重置链接无效或已过期'})
    
    # 更新用户密码
    user = User.query.get(reset_request.user_id)
    user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
    
    # 标记重置请求完成
    reset_request.status = 'completed'
    reset_request.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': '密码重置成功，请使用新密码登录'})

@app.route('/api/check-password-strength', methods=['POST'])
def check_password_strength_api():
    """检查密码强度API"""
    password = request.json.get('password')
    if not password:
        return jsonify({'success': False, 'message': '请输入密码'})
    
    result = check_password_strength(password)
    return jsonify({'success': True, 'data': result})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
