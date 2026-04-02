import json
import logging
import os
from json import JSONDecodeError
from pathlib import Path
from typing import Dict, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session
from app.exceptions.http_exceptions import NotFoundError, ValidationError
from app.models.resume import Resume
from app.services.client.ai_service import AIService

logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads/resumes"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class ResumeService:
    @staticmethod
    async def create_resume_upload(
        db: AsyncSession,
        user_id: int,
        file_content: bytes,
        file_name: str,
        target_position: str,
    ) -> Dict:
        """保存上传的简历文件，并立即创建解析记录。"""
        safe_name = Path(file_name or "resume.pdf").name or "resume.pdf"
        file_path = os.path.join(UPLOAD_DIR, f"{user_id}_{uuid4().hex}_{safe_name}")

        try:
            with open(file_path, "wb") as f:
                f.write(file_content)
        except OSError as exc:
            logger.exception("Save resume file failed: %s", exc)
            raise ValidationError(message="简历文件保存失败，请稍后重试") from exc

        resume = Resume(
            user_id=user_id,
            file_url=file_path,
            file_name=safe_name,
            target_position=target_position,
            status="parsing",
        )
        db.add(resume)
        await db.commit()
        await db.refresh(resume)

        return {
            "resume_id": resume.id,
            "status": resume.status,
            "message": "简历上传成功，正在解析",
        }

    @staticmethod
    async def process_resume(
        resume_id: int,
        ai_config: Optional[Dict] = None,
    ) -> None:
        """在后台异步解析简历，避免上传接口长时间阻塞。"""
        async with async_session() as db:
            result = await db.execute(select(Resume).where(Resume.id == resume_id))
            resume = result.scalar_one_or_none()
            if not resume:
                logger.warning("Resume %s not found for background processing", resume_id)
                return

            await ResumeService._process_resume_record(db, resume, ai_config=ai_config)

    @staticmethod
    async def _process_resume_record(
        db: AsyncSession,
        resume: Resume,
        ai_config: Optional[Dict] = None,
    ) -> None:
        try:
            resume_text = ResumeService._extract_pdf_text(resume.file_url or "")
            if not resume_text.strip():
                raise ValidationError(message="无法从 PDF 中提取文本内容")
        except ValidationError as exc:
            await ResumeService._mark_resume_failed(db, resume, exc.detail)
            return
        except Exception as exc:
            logger.exception("PDF parse failed for resume %s: %s", resume.id, exc)
            await ResumeService._mark_resume_failed(db, resume, f"PDF 解析失败: {str(exc)}")
            return

        try:
            parsed = await AIService.parse_resume(resume_text, ai_config=ai_config)
            resume.parsed_content = json.dumps(parsed, ensure_ascii=False)

            analysis = await AIService.analyze_resume(
                parsed,
                resume.target_position or "",
                ai_config=ai_config,
            )
            resume.analysis = json.dumps(analysis, ensure_ascii=False)
            resume.status = "completed"
            await db.commit()
            await db.refresh(resume)
        except ValidationError as exc:
            await ResumeService._mark_resume_failed(db, resume, exc.detail)
        except JSONDecodeError as exc:
            logger.exception("Resume AI JSON parse failed for resume %s: %s", resume.id, exc)
            await ResumeService._mark_resume_failed(
                db,
                resume,
                "AI 返回格式异常，请稍后重试或更换模型",
            )
        except Exception as exc:
            logger.exception("Resume AI processing failed for resume %s: %s", resume.id, exc)
            await ResumeService._mark_resume_failed(
                db,
                resume,
                "简历解析服务异常，请稍后重试",
            )

    @staticmethod
    async def _mark_resume_failed(
        db: AsyncSession,
        resume: Resume,
        error_message: str,
    ) -> None:
        resume.status = "failed"
        resume.analysis = json.dumps({"error_message": error_message}, ensure_ascii=False)
        await db.commit()

    @staticmethod
    def _extract_pdf_text(file_path: str) -> str:
        """从 PDF 文件中提取文本内容。"""
        import pdfplumber

        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text

    @staticmethod
    async def get_resume(db: AsyncSession, resume_id: int, user_id: int) -> Dict:
        """根据 ID 获取简历详情。"""
        query = select(Resume).where(
            Resume.id == resume_id,
            Resume.user_id == user_id,
        )
        result = await db.execute(query)
        resume = result.scalar_one_or_none()

        if not resume:
            raise NotFoundError(message="简历不存在")

        parsed_content = None
        if resume.parsed_content:
            try:
                parsed_content = json.loads(resume.parsed_content)
            except json.JSONDecodeError:
                parsed_content = None

        analysis = None
        error_message = None
        if resume.analysis:
            try:
                analysis = json.loads(resume.analysis)
                if isinstance(analysis, dict):
                    error_message = analysis.get("error_message")
            except json.JSONDecodeError:
                analysis = None

        return {
            "resume_id": resume.id,
            "status": resume.status,
            "file_name": resume.file_name,
            "target_position": resume.target_position,
            "parsed_content": parsed_content,
            "analysis": analysis,
            "error_message": error_message,
            "created_at": resume.created_at.isoformat() if resume.created_at else None,
        }

    @staticmethod
    async def get_user_resumes(db: AsyncSession, user_id: int) -> list:
        """获取用户的所有简历列表。"""
        query = select(Resume).where(
            Resume.user_id == user_id
        ).order_by(Resume.created_at.desc())
        result = await db.execute(query)
        resumes = result.scalars().all()

        return [
            {
                "resume_id": r.id,
                "file_name": r.file_name,
                "target_position": r.target_position,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in resumes
        ]


resume_service = ResumeService()
